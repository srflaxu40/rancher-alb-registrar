# alb-registrar

@TO-DO - Dynamically update spotinst elastigroups based on environment with target group names.  This is because spotinst uses target groups, and
 not alb names.
@TO-DO - Delete old target groups (no longer used or usurped) after 'x' amount of time.   This is to allow rollback while also providing cleanup.

_Dynamically Updating your ALB things_

  * This project's purpose is to allow the specification of custom labels in order to schedule, update, and create
    new or existing target groups.  This allows the deployment of an application to a new target group, its updating
    of an Application Load Balancer (ALB) in AWS side by side with the current (primary) target group.  Through this
    functionality, dark-releases can be achieved which allows the live testing of an application in prod.  Upon release,
    the primary rule in the ALB is simply updated to the dark-release target group allowing zero down time, and 
    seamless deployments to production, et al, without rollbacks, without show stopping bugs, and without the need
    to immediately rush around hot-fixing issues.  This provides the ability to Dark Release.

## Notes:
  
  * Tested with rancher/server:v1.1.4, and rancher/agent:v1.0.2.
  * To test this project locally you need AWS access so you can manipulate ALBs.  You also need to install rancher
    locally, or have access to the dev environment to run and test your rancher-compose modifications.
    * [rancher/server](https://docs.rancher.com/rancher/v1.3/en/installing-rancher/installing-server/)

## How to setup aws cli:

  * Upgrade the `aws` cli:

    * `pip install -U aws`
    * Be sure to setup your AWS creds properly (environment or ~/.aws/credentials)!

  * , Or install it if you haven't:
    * http://docs.aws.amazon.com/cli/latest/userguide/installing.html

  * MUST MUST MUST run-me (if you don't setup your AWS creds above):
    * `aws configure`

  * Ensure you have the right version that supports ELBv2:
    * `aws elbv2 help`

  * Some helpful aws elbv2 commands:
    * `aws elbv2 describe-listeners --load-balancer-arn <load balancer arn>`
    * `aws elbv2 describe-target-groups --load-balancer-arn <load balancer arn>`
    * `aws elbv2 describe-target-groups --name matador-tres`

  * After configuring AWS on your local machine, sym-link it over to this GitHub cloned repo so you can build your Docker image.
  * Note that this is for local use only as the deployed service works off IAM roles.
    * `ln -s ~/.aws .aws`

## Development Setup:

  * Just run me baby:
    * `./alb_registrar_daemon.py <( URL | port | domain )>`

---

## Rancher Compose Label Configuration.

* Add the following labels to your rancher compose file:
  * `alb-registrar` - Whether this stack is to be watched or updated by the alb-registrar service.  If true, the following labels
     need to also be added otherwise it will not work.
  * `alb-name` - The Application Load Balancer (ALB) to update.  ALB Load Balancer names should take on the form `<application>-<environment>` where
     environment is one of three values:
     * develop
     * staging
     * production
  * `alb-target-group` - The target group (existing or not) to either update or create.
  * `alb-path` - The path / rule to place the newly created target group under.  Note that existing target groups are already a 
     part of a rule, and thereby the rule does not need upating as the target group already exists in the rule in the ALB.
     * This path must exist as a set RULE in the ALB.  The rule's port doesn't matter as any new or to-be updated target groups do not rely on ports
       for updating.  If the path does not exist, no rule will be updated because the alb-registrar service will not be able to find the rule to udpate.

```
  labels:
    ...
    alb-registrar: "true"
    alb-name: "penguin-brigade-alb-production"
    alb-target-group: "your-hot-new-target-group"
    alb-path: "/green"
```

* Additionally, the following host-less port mapping _must_ be set in your rancher compose file:

```
penguin-app:
  image: johndoehub/penguin-brigade:latest
  ports:
  - 3000/tcp
  stdin_open: true
  tty: true
  ...
```

  * The host-less port mapping allows Rancher to choose from a randomly available host-port across the stack.  This affords the ability to 
    dynamically update the ALBs via target groups while not having to bring down the existing service.  It also allows the ability to dark-release
    applications, their testing in a live environment, and when meant to go live simply updating an ALB rule to use the new target group.
  * By specifying an _existing_ target group, the ALB will simply register the new instances into the existing target group on their new host
    ports _first_, and then de-register the old targets.  This is seamless, and there is no downtime.

### Example:
  * If a target group exists, host ports are compared to current ports of the the currently registered instances (registered with the target group).
    * If they are the same, the stack is skipped as this implies it is the old stack.  If they are different, the target group must be updated
      with newly registered instances with the new port, which will automatically override the target group port; this is a behavior implemented
      by AWS and not the registrar.

```
jknepper@MacBook-Pro-5:~/alb-registrar> docker-compose up
Recreating albregistrar_alb-registrar_1
Attaching to albregistrar_alb-registrar_1
alb-registrar_1  | URL: 192.168.0.15
alb-registrar_1  | another iteration...
alb-registrar_1  | Port to update to: 52611 from old port: 20012
alb-registrar_1  | resetting ports for: matador-tres
alb-registrar_1  | Id: i-0d714e0179f37fded to be registered with port: 52611
alb-registrar_1  | Id: i-084ed5272ad836b42 to be registered with port: 52611
alb-registrar_1  | Id: i-01d1aca22020c2272 to be registered with port: 52611
alb-registrar_1  | Id: i-0235ff9e7130495c0 to be registered with port: 52611
alb-registrar_1  | URL: 192.168.0.15
alb-registrar_1  | another iteration...
alb-registrar_1  | URL: 192.168.0.15
alb-registrar_1  | another iteration...
alb-registrar_1  | URL: 192.168.0.15
alb-registrar_1  | another iteration...
alb-registrar_1  | URL: 192.168.0.15
```

  * As the script iterates in a loop, it checks all containers via the Rancher API to see if the individual service was deployed with the `alb-*`
    labels.  When it finds a service with the label, it either creates the target group registering it with currently registered instances in
    other target groups that are a part of the current ALB's setup or it updates the existing target group by registering it with new ports of
    the newly deployed service.  The reason this creation mechanism works is because currently registered instances must be active hosts otherwise
    the ALB would be out of service and fail health checks in AWS.
  * Notice the compose file exerpt:

```
  labels:
    io.rancher.scheduler.global: "true"
    alb-registrar: "true"
    alb-name: "operation-johnson-n-johnson"
    alb-target-group: "matador-tres"
```

  * The currently deployed service (in Rancher) is listening on the host port 52611:
![Alt text](/images/current.png?raw=true "Current Ports")

  * Re-deploying this stack with a new project name brings up an entirely new stack side-by-side to the current stack.  This stack shares different ports
    than the original.  Since the stack's compose file has the _same_ target-group label name (_alb-target-group: "matador-tres"_) as the previous stack
    it will register the new instances with the current target group (in our case matador-tres) and de-register the old instances.  New targets for the 
    target group _matador-tres_ will now be registered with the new ports of project _matador-2_ (see newly deployed stack in image below).  This seamless deployment replaces the existing stack,
    which still exists and can be rolled back (highly unlikely in this use-case as deploying directly to an environment implies intentful malice. haha).
    * Note that target group attributes contain a draining value of zero (0); TO-DO - create paramaterized draining.
  * The newly deployed stack with new host ports:
![Alt text](/images/new_stack.png?raw=true "Newly Deployed Stack")
  * The registrar service runs in an infinite loop, polls the Rancher API, notices the newly deployed stack's ports are not the same as the current ports
    in the target group _matador-tres_ and updates the target group's registered instances with the new port.  After updating, it immediately removes
    the old instance / port mappings from the target group:

```
jknepper@MacBook-Pro-5:~/alb-registrar> docker-compose up
Starting albregistrar_alb-registrar_1
Attaching to albregistrar_alb-registrar_1
alb-registrar_1  | URL: 192.168.0.15
alb-registrar_1  | another iteration...
alb-registrar_1  | Port to update to: 51061 from old port: 52611
alb-registrar_1  | resetting ports for: matador-tres
alb-registrar_1  | Id: i-0235ff9e7130495c0 to be registered with port: 51061
alb-registrar_1  | Id: i-084ed5272ad836b42 to be registered with port: 51061
alb-registrar_1  | Id: i-0d714e0179f37fded to be registered with port: 51061
alb-registrar_1  | Id: i-01d1aca22020c2272 to be registered with port: 51061
alb-registrar_1  | URL: 192.168.0.15
alb-registrar_1  | another iteration...
```

![Alt text](/images/updated.png?raw=true "Updated Target Group with targets pointing to new ports of new service / stack deployed in Rancher.")

### Example:

  * If a target group name specified with the Rancher label `alb-target-group` does not exist, the registrar automatically creates it and (TO-DO) 
    updates the ALB rule to point at it via the rule containing _alb-path_:

```
  labels:
    io.rancher.scheduler.global: "true"
    alb-registrar: "true"
    alb-name: "operation-johnson-n-johnson"
    alb-target-group: "matador-tres"
    alb-path: "/green"
```

```
jknepper@MacBook-Pro-5:~/alb-registrar> docker-compose up
jknepper@MacBook-Pro-5:~/alb-registrar> ./alb_registrar_daemon.py 127.0.0.1
URL: 127.0.0.1
another iteration...
creating target group: matador-cinco
Creating target group with name: matador-cinco and host port: 53726
Registering instance id: i-0d714e0179f37fded to target group: matador-cinco on Port: 53726 inside method create_target_group()
Registering instance id: i-084ed5272ad836b42 to target group: matador-cinco on Port: 53726 inside method create_target_group()
Registering instance id: i-01d1aca22020c2272 to target group: matador-cinco on Port: 53726 inside method create_target_group()
Registering instance id: i-0235ff9e7130495c0 to target group: matador-cinco on Port: 53726 inside method create_target_group()
Updating load balancer: operation-johnson-n-johnson with target group: matador-cinco that has arn: arn:aws:elasticloadbalancing:us-west-1:038136765190:targetgroup/matador-cinco/942a019657d61beb
Updating listener rule...
Target group to assign to rule: arn:aws:elasticloadbalancing:us-west-1:038136765190:targetgroup/matador-cinco/942a019657d61beb
Rule being updated: arn:aws:elasticloadbalancing:us-west-1:038136765190:listener-rule/app/operation-johnson-n-johnson/b050200b856f9549/1613d2b7ed4de54c/b644d3dda48f19db
Rule updated...
URL: 127.0.0.1
another iteration...
URL: 127.0.0.1
```

*Newly Created Target Group:*
![Alt text](/images/created_tg.png?raw=true "Newly Created Target Group.")

*Updated Rule:*
![Alt text](/images/updated_rule.png?raw=true "Rule containing path specified with the Rancher Compose label alb-path updated with newly created Target Group ARN..")

---

## Docker:

  *  Build It:
    * `docker build --build-arg URL=192.168.0.15 --no-cache -t alb-registrar .`
    * `docker run -e RANCHER_ACCESS_KEY=<rancher access key value> -e RANCHER_SECRET_KEY=<rancher secret key value> -it alb-registrar`

## Docker Compose:

  * Build it from scratch:

```
_$ export URL=<url to rancher>
_$ docker-compose up
...
```
