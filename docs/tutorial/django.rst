Deploying Django at Amazon
==========================

We will deploy the sentry service at Amazon with Touchdown. Sentry is a Django
application so much of this will be applicable to any Django application. This
walkthrough will touch on:

 * Creating a :class:`~touchdown.aws.vpc.vpc.VPC` with multiple interconnected
   :class:`~touchdown.aws.vpc.subnet.Subnet`'s.

 * Creating a :class:`~touchdown.aws.rds.Database` and passing its connection
   details to the Django instance.

 * Using an :class:`~touchdown.aws.ec2.AutoScalingGroup` to start an instance.

 * Using a :class:`~touchdown.aws.elb.LoadBalancer` to scale up your service.


Desiging your network
---------------------

We will create a subnet for each type of resource we plan to deploy. For our
demo this means there will be 3 subnets:

 =======   ===================   ==================
 segment   network               ingress
 =======   ===================   ==================
 lb        ``192.168.0.0/24``    ``0.0.0.0/0:80``
                                 ``0.0.0.0/0:443``
 app       ``192.168.1.0/24``    ``lb:80``
 db        ``192.168.2.0/24``    ``app:5432``
 =======   ===================   ==================

The only tier that will have public facing IP's is the lb tier.

First we'll create a 3 subnet VPC::

    vpc = aws.add_vpc('sentry')

    subnets = {
        'lb': vpc.add_subnet(
            name="lb",
            cidr_block='192.168.0.0/24',
        ),
        'app': vpc.add_subnet(
            name="app",
            cidr_block='192.168.1.0/24',
        ),
        'db': vpc.add_subnet(
            name="db",
            cidr_block='192.168.2.0/24',
        ),
    }

Then we'll create security groups that limit who can access the subnets::

    security_groups = {}
    security_groups['lb'] = vpc.add_security_group(
        name="lb",
        ingress=[
            {"port": 80, "network": "0.0.0.0/0"},
            {"port": 443, "network": "0.0.0.0/0"},
        ],
    )
    security_groups['app'] = vpc.add_security_group(
        name="app",
        ingress=[
            {"port": 80, "security_group": security_groups["lb"]},
        ],
    )
    security_groups['db'] = vpc.add_security_group(
        name="db",
        ingress=[
            {"port": 5432, "security_group": security_groups["app"]},
        ],
    )


Adding a database
-----------------

Rather than manually deploying postgres on an EC2 instance we'll use RDS to
provision a managed :class:`~touchdown.aws.rds.Database`::

    database = aws.add_database(
        name=sentry,
        allocated_storage=10,
        instance_class='db.t1.micro',
        engine="postgres",
        db_name="sentry",
        master_username="sentry",
        master_password="password",
        backup_retention_period=8,
        auto_minor_version_upgrade=True,
        publically_accessible=False,
        storage_type="gp2",
        security_groups=[security_groups['db']],
        subnet_group=aws.add_db_subnet_group(
            name="sentry",
            subnets=subnets['db'],
        )
    )


Building your base image
------------------------

We'll setup a fuselage bundle to describe what to install on the base ec2
image::

    provisioner = workspace.add_fuselage_bundle()

One unfortunate problem with Ubuntu 14.04 is that you can SSH into it before it
is ready. ``cloud-init`` is still configuring it, and so if you start deploying
straight away you will hit race conditions. So we'll wait for ``cloud-init`` to
finish::

    # Work around some horrid race condition where cloud-init hasn't finished running
    # https://bugs.launchpad.net/cloud-init/+bug/1258113
    provisioner.add_execute(
        command="python -c \"while not __import__('os').path.exists('/run/cloud-init/result.json'): __import__('time').sleep(1)\"",
    )

Then we'll install some standard python packages::

    provisioner.add_package(name="python-virtualenv")
    provisioner.add_package(name="python-dev")
    provisioner.add_package(name="libpq-dev")

We are going to deploy the app into a virtualenv at ``/app``. We'll do the
deployment as root, and at runtime the app will use the `sentry` user. We'll
create a ``/app/etc`` directory to keep settings in::

    provisioner.add_group(name="django")

    provisioner.add_user(
        name="django",
        group="django",
        home="/app",
        shell="/bin/false",
        system=True,
    )

    provisioner.add_directory(
        name='/app',
        owner='root',
        group='root',
    )

    provisioner.add_directory(
        name='/app/etc',
        owner='root',
        group='root',
    )

    provisioner.add_directory(
        name='/app/var',
        owner='root',
        group='root',
    )

    provisioner.add_execute(
        name="virtualenv",
        command="virtualenv /app",
        creates="/app/bin/pip",
        user="root",
    )

We'll inject a requirements.txt and install sentry into the virtualenv::

    provisioner.add_file(
        name='/app/requirements.txt',
        contents='\n'.join(
            'sentry==7.5.3',
        )
    )

    provisioner.add_execute(
        command="/app/bin/pip install -r /app/requirements.txt",
        watches=['/app/requirements.txt'],
    )

This uses the `watches` syntax. This means we only update the virtualenv if
requirements.txt has changed and is one mechanism for idempotence when using the
``Execute`` resource.

We need to actually start sentry. We'll use upstart for this::

    provisioner.add_file(
        name="/etc/init/kickstart.conf",
        contents="\n".join([
           "start on runlevel [2345]",
           "task",
           "exec /app/bin/sentry kickstart",
        ]),
    )

``kickstart`` is a command we'll create that loads metadata such as the database
username and password from AWS. It will use ``initctl emit`` to tell upstart
other tasks it might need to start.

We'll also need upstart configuration for the django app server and for the
celery processes::

    provisioner.add_file(
        name="/etc/init/application.conf",
        contents="\n".join([
            "start on mode-application",
            "stop on runlevel [!2345]",
            "setuid sentry",
            "setgid sentry",
            "kill timeout 900",
            "respawn",
            " ".join([
                "exec /app/bin/gunicorn -b 0.0.0.0:8080",
                "--access-logfile -",
                "--error-logfile -",
                "--log-level DEBUG",
                "-w 8",
                "-t 120",
                "--graceful-timeout 120",
                "sentry.wsgi",
            ]),
        ]),
    )

    provisioner.add_file(
        name="/etc/init/worker.conf",
        contents="\n".join([
            "start on mode-worker",
            "stop on runlevel [!2345]",
            "setuid sentry",
            "setgid sentry",
            "kill timeout 900",
            "respawn",
            "exec /app/bin/django celery worker --concurrency 8",
        ]),
    )

    provisioner.add_file(
        name="/etc/init/beat.conf",
        contents="\n".join([
            "start on mode-beat",
            "stop on runlevel [!2345]",
            "setuid sentry",
            "setgid sentry",
            "kill timeout 900",
            "respawn",
            "exec /app/bin/django celery beat --pidfile=",
        ]),
    )

To actually provision this as an AMI we use the
:class:`~touchdown.aws.ec2.Image` resource::

    image = aws.add_image(
        name="sentry-demo",
        source_ami='ami-d74437a0',
        username="ubuntu",
        provisioner=provisioner,
    )


Deploying an instance
---------------------

We'll deploy the image we just made with an auto scaling group. We are going to
put a load balancer in front, which we'll set up first::

    lb = aws.add_load_balancer(
        name='balancer',
        listeners=[
            {"port": 80, "protocol": "http", "instance_port": 8080, "instance_protocol": "http"}
        ],
        subnets=subnets['lb'],
        security_groups=[security_groups['lb']],
        health_check={
            "interval": 30,
            "healthy_threshold": 3,
            "unhealthy_threshold": 5,
            "check": "HTTP:8080/__ping__",
            "timeout": 20,
        },
        attributes={
            "cross_zone_load_balancing": True,
            "connection_draining": 30,
        },
    )


We are going to set some user data in the AutoScaling setup so that Django knows which database to connect to.

    user_data = serializers.Json(serializers.Dict({
        "DATABASES": serializers.Dict(
            ENGINE='django.db.backends.postgresql_psycopg2',
            NAME=database.db_name,
            HOST=serializers.Format("{0[Address]}", database.get_property("Endpoint")),
            USER=database.master_username,
            PASSWORD=database.master_password,
            PORT=5432,
            ),

    }))


Then we need a :class:`~touchdown.aws.ec2.LaunchConfiguration` that says what
any started instances should look like and the
:class:`~touchdown.aws.ec2.AutoScalingGroup` itself::

    app = aws.add_auto_scaling_group(
        name="sentry-app",
        launch_configuration=aws.add_launch_configuration(
            name="sentry-app",
            image=ami,
            instance_type="t1.micro",
            user_data=user_data,
            key_pair=keypair,
            security_groups=security_groups["app"],
            associate_public_ip_address=False,
        ),
        min_size=1,
        max_size=1,
        load_balancers=[lb],
        subnets=subnets["app"],
    )
