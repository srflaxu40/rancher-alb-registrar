#!/usr/local/bin/python

import urllib2, sys, json, time, subprocess, re, base64

# NOTES:
# python alb_registrar_daemon.py <url like 127.0.0.1 or rancher.masterorip.com> <RANCHER ACCESS KEY> <RANCHER SECRET KEY>
# Current supported docker compose version v1

# TO-DO: add get-opts.
# TO-DO: make OOP
# TO-DO: Add verbosity to get-opts for greater debugging.

# Return a list of containers with label alb-registrar
def get_alb_labeled_containers():

    containerData = None

    try:
        url = "https://" + sys.argv[1] + "/v1?limit=1000"

        passman  = urllib2.HTTPPasswordMgrWithDefaultRealm()
        passman.add_password(None, url, sys.argv[2], sys.argv[3])
        urllib2.install_opener(urllib2.build_opener(urllib2.HTTPBasicAuthHandler(passman)))

        req      = urllib2.Request(url)
        response = urllib2.urlopen(req)

        html     = response.read()
        jsonObj  = json.loads(html) 

        url = "https://" + sys.argv[1] + "/v1/containers?limit=1000"

        passman  = urllib2.HTTPPasswordMgrWithDefaultRealm()
        passman.add_password(None, url, sys.argv[2], sys.argv[3])
        urllib2.install_opener(urllib2.build_opener(urllib2.HTTPBasicAuthHandler(passman)))

        req      = urllib2.Request(url)
        response = urllib2.urlopen(req)
        html     = response.read()

        containerData  = json.loads(html) 

    except subprocess.CalledProcessError as e:
        print e.output
    

    for entry in containerData["data"]:

        if "alb-registrar" in entry["labels"]:

            # This case should not happen, but you know there is always a Timmy Tulip that
            # cannot follow instructions:
            if entry["labels"]["alb-registrar"] == False:
                continue

            resultBool     = target_exist(entry["labels"]["alb-target-group"])
            targetGroup    = None

            # If target exists, just registered ports
            if resultBool:
                targetGroup = entry["labels"]["alb-target-group"]

                arn         = get_target_group_arn( targetGroup)
                groupPort   = str(get_target_group_port( targetGroup ))

                if groupPort == 0:
                    print "No targets in target group."

                containerPortMapping = entry["ports"]
                hostPort             = str(get_host_port( containerPortMapping[0] ))

                if hostPort == groupPort:
                    continue
           
                print "Port to update to: " + hostPort + " from old port: " + groupPort
                print "resetting ports for: " + targetGroup 

                # TO-DO - setup some sort of notification handler to notify slack or AWS lambda
                set_register_target_ports( hostPort, targetGroup, arn )
                
            # Otherwise, create the target:
            else:
                targetGroup = entry["labels"]["alb-target-group"]
                albName     = entry["labels"]["alb-name"]
                albPath     = entry["labels"]["alb-path"]

                print "creating target group: " + targetGroup

                albArn   = get_alb_arn( albName )
                vpcId    = get_vpc_id( albName )

                containerPortMapping = entry["ports"]
                hostPort             = get_host_port( containerPortMapping[0] )
            
                targetGroupArn       = create_target_group( albName, targetGroup, vpcId, hostPort )
                print "Updating load balancer: " + albName + " with target group: " + targetGroup + " that has arn: " + targetGroupArn

                update_load_balancer_listener( albName, targetGroup, albArn, targetGroupArn, albPath )
                

# Get liseners from alb:
def get_listeners( alb_arn ):
    try:
        groupResponse  = subprocess.check_output(["aws", "elbv2", "describe-listeners", "--load-balancer-arn", alb_arn])
        groupJson = json.loads(groupResponse)

        return groupJson
    except subprocess.CalledProcessError as e:
        print e.output

# get / describe listener rules:
def get_rule( listeners, alb_path ):
    try:
       
        for listener in listeners["Listeners"]:
            groupResponse  = subprocess.check_output(["aws", "elbv2", "describe-rules", "--listener-arn", listener["ListenerArn"]])
            groupJson = json.loads(groupResponse)

            for rule in groupJson["Rules"]:
                conditions = rule["Conditions"]
                for condition in conditions:
                    value = condition["Values"]
                    if value[0] == alb_path:
                        return rule

    except subprocess.CalledProcessError as e:
        print e.output


# Update load balancer listener rule identified by the label alb-path to point at the new target group:
def update_load_balancer_listener( alb_name, target_group, alb_arn, target_group_arn, alb_path ):
    listeners = get_listeners( alb_arn )

    try: 
        rule = get_rule( listeners, alb_path )
        try:
            # aws elbv2 modify-rule --rule-arn
            print "Updating listener rule..."
            print "Target group to assign to rule: " + target_group_arn
            print "Rule being updated: " + rule["RuleArn"]
            groupResponse  = subprocess.check_output(["aws", "elbv2", "modify-rule", "--rule-arn", rule["RuleArn"], "--action", "Type=forward,TargetGroupArn=" + target_group_arn])
            groupJson = json.loads(groupResponse)

            print "Rule updated..."

        except subprocess.CalledProcessError as e:
            print e.output
    except subprocess.CalledProcessError as e:
        print e.output
        
# Get VPC ID:
def get_vpc_id( alb_name ):

    try:
        groupResponse  = subprocess.check_output(["aws", "elbv2", "describe-load-balancers", "--name", alb_name])
        groupJson = json.loads(groupResponse)

        vpc_id    =  groupJson["LoadBalancers"][0]["VpcId"]

        return vpc_id
    except subprocess.CalledProcessError as e:
        print e.output

# Get alb arn:
def get_alb_arn( alb_name ):

    try:
        groupResponse  = subprocess.check_output(["aws", "elbv2", "describe-load-balancers", "--name", alb_name])
        groupJson      = json.loads(groupResponse)
        albArn         =  groupJson["LoadBalancers"][0]["LoadBalancerArn"]

        return albArn
    except subprocess.CalledProcessError as e:
        print e.output

# Create target group if it doesn't exist:
def create_target_group( alb_name, group_name, vpc_id, host_port ):

    createResponse = None
    new_target_arn = None

    try:
        # TO-DO: Add healthcheck label to docker compose rancher YAML to allow dynamic selection of healthchecks.
        # TO-DO: Add http check protocol as label to d.c.r. yaml.
        # TO-DO: Add protocol as label to d.c.r. yaml.
        print "Creating target group with name: " + group_name + " and host port: " + host_port

        createResponse = subprocess.check_output(["aws", "elbv2", "create-target-group", \
        "--name", group_name, "--protocol", "HTTP", "--port", host_port, "--vpc-id", vpc_id, \
        "--health-check-protocol", "HTTP", "--health-check-port", "traffic-port",  "--health-check-path", \
        "/healthcheck", "--health-check-interval-seconds", "6", "--health-check-timeout-seconds", "5",  \
        "--healthy-threshold-count", "5", "--unhealthy-threshold-count", "2", "--matcher", "HttpCode=200"])

        groupJson      = json.loads(createResponse)
        new_target_arn = groupJson["TargetGroups"][0]["TargetGroupArn"]

        # Update target group attributes to hasten draining.  Drain immediately.
        subprocess.check_output(["aws", "elbv2", "modify-target-group-attributes", "--target-group-arn", new_target_arn, "--attributes", "Key=deregistration_delay.timeout_seconds,Value=0"])

        alb_arn = get_alb_arn( alb_name )
        groupResponse  = subprocess.check_output(["aws", "elbv2", "describe-target-groups", "--load-balancer-arn", alb_arn])
        groupJson      = json.loads(groupResponse)

        name           = get_target_group_arn( groupJson["TargetGroups"][0]["TargetGroupName"] )

        targets = get_targets(name)

        for target in targets:

            if target["TargetHealth"]["State"] == "draining":
                continue

            id = target["Target"]["Id"]

            print "Registering instance id: " + id + " to target group: " + group_name + " on Port: " + host_port + " inside method create_target_group()"

            # Register new instance:
            subprocess.check_output(["aws", "elbv2", "register-targets", "--target-group-arn", new_target_arn, "--targets", "Id=" + id + ",Port=" + host_port])

 
        arn = get_target_group_arn( group_name )

        return arn
    except subprocess.CalledProcessError as e:
        print e.output

# Return target group port to ensure updated to current host value:
# Note - we want target port as target group port is / can be overridden,
# and thereby is unreliable.
def get_target_group_port( target_group ):
    try:
        arn = get_target_group_arn( target_group)

        groupResponse = subprocess.check_output(["aws", "elbv2", "describe-target-health", "--target-group-arn", arn])
        groupJson     = json.loads(groupResponse)
        targets       = groupJson["TargetHealthDescriptions"]

        port = None

        if len(targets) == 0:
            return 0
        else:
            port =  targets[0]["Target"]["Port"]

        return port

    except subprocess.CalledProcessError as e:
        print e.output

# Get target group ARN from AWS:
def get_target_group_arn( target_group ):
    try:
        groupResponse  = subprocess.check_output(["aws", "elbv2", "describe-target-groups", "--name", target_group])
        groupJson      = json.loads(groupResponse)
        arn            = groupJson["TargetGroups"][0]["TargetGroupArn"]
        return arn
    except subprocess.CalledProcessError as e:
        print e.output

# Return the host port container is randomly mapped to:
def get_host_port( port_string):
    m    = re.search('^\d+', port_string)
    port = m.group(0)
    return port

# Check if target group exists:
def target_exist( target_group ):
    try:
        groupResponse = subprocess.check_output(["aws", "elbv2", "describe-target-groups"])
        groupJson     = json.loads(groupResponse)
    
        existBool     = False

        for group in groupJson["TargetGroups"]:
            groupName     = group["TargetGroupName"]

            if groupName == target_group:
                existBool = True
                return existBool

        return existBool
    except subprocess.CalledProcessError as e:
        print e.output


# Return list of current / active targets in target group:
def get_targets( arn ):
    groupResponse = subprocess.check_output(["aws", "elbv2", "describe-target-health", "--target-group-arn", arn])
    groupJson     = json.loads(groupResponse)
    targets       = groupJson["TargetHealthDescriptions"]
    return targets

# Get instances, and register them:
def set_register_target_ports( register_port, target_group, arn ):
    targets = get_targets(arn)
    oldPort = None

    for target in targets:
        id = target["Target"]["Id"]

        print "Id: " + id + " to be registered with port: " + register_port

        try:
            # Register new instance:
            subprocess.check_output(["aws", "elbv2", "register-targets", "--target-group-arn", arn, "--targets", "Id=" + id + ",Port=" + register_port])

            oldPort = str(target["Target"]["Port"])

            # De-register old instance:
            subprocess.check_output(["aws", "elbv2", "deregister-targets", "--target-group-arn", arn, "--targets", "Id=" + id + ",Port=" + oldPort])

        except subprocess.CalledProcessError as e:
            print e.output


# Continually iterate and do your thing:
while 1:

    print "URL: " + sys.argv[1]
    print "another iteration..."

    # change this into an argument in the future to slow the pace of processing.
    time.sleep(5)
    get_alb_labeled_containers()

