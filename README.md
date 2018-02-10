# Websubsub

Django websub subscriber.

## Installation

```
pip install websubsub
```

Add `websubsub.apps.WebsubsubConfig` to the list of `INSTALLED_APPS` in your `settings.py`:

```
INSTALLED_APPS = [
    ...,
    'websubsub.apps.WebsubsubConfig'
]
```

## Usage

### Create Websub callback
Create celery task handler, usually in `tasks.py`:

```
from celery import shared_task

@shared_task
def news_task(data):
    print('got news!')
```

Callback url should end with uuid. Register url for handler in `urls.py`:

```
from websubsub.views import WssView
from .tasks import news_task, reports_task

urlpatterns = [
    path('/websubcallback/news/<uuid:id>', WssView.as_view(news_task), name='webnews')
    path('/websubcallback/reports/<uuid:id>', WssView.as_view(reports_task), name='webreports')
]
```

### Subscribe

Set the `SITE_URL` setting in your `settings.py` to the full url of your project site, e.g.
`https://example.com`. It will be used to build full callback urls.

Set `WEBSUBS_REDIS_URL` settings in your `settings.py`. Redis locks are used to ensure
subscription\unsubscription tasks are consistent with hub and local database.

You can create subscription on the go, or use static subscriptions.

To create subscription in the code:

```
from websubsub.models import Subscription
Subscription.create(topic='mytopic', urlname='webnews', hub='http://example.com')
```

This will create Subscription object in the database and schedule celery task
to subscribe with hub.

#### Static subscriptions

[TODO] Not sure it is the best way to handle static subscriptions.

Static subscriptions can be defined in your `settings.py`, they are then materialized
with management command `./manage.py websubscribe_static`.

Add static subscriptions in your `settings.py`:

```
WEBSUBS_HUBS = {
    'http://example.com': {
        'subscriptions': [
            # (topic, urlname) pairs
            ('mytopic', 'webnews'),
            ...
        ]
    }
}
```

Execute `./manage.py websubscribe_static`

## Discovery

Not implemented

## Settings

`SITE_URL` - ex.: `https://example.com`. Required. Will be used to build full callback urls.

`WEBSUBS_REDIS_URL` - ex.: `redis://redishost:6379`. Required. Will be used to lock atomic tasks.

`WEBSUBS_DEFAULT_HUB_URL`

`WEBSUBS_MAX_CONNECT_RETRIES`

`WEBSUBS_MAX_HUB_ERROR_RETRIES`

`WEBSUBS_MAX_VERIFY_RETRIES`

`WEBSUBS_VERIFY_WAIT_TIME`