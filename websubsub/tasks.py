import logging
from datetime import timedelta
from os.path import join
from uuid import uuid4

from celery import shared_task
from django.conf import settings
from django.db.models import Q
from django.urls import reverse, Resolver404
from django.utils.timezone import now
from requests import post
from rest_framework import status

from .lock import lock_or_exit, lock_wait
from .models import Subscription

logger = logging.getLogger('websubsub.tasks')


@shared_task
def refresh_subscriptions():
    """
    This task should be scheduled to launch periodically
    """
    soon = now() + timedelta(days=1)  # TODO: setting
    _filter = {
        'lease_expiration_time__le': soon,
        'unsubscribe_status__isnull': True  # Exclude explicitly unsubscribed
    }
    for ssn in Subscription.objects.filter(**_filter):
        subscribe.delay(pk=ssn.pk)


@shared_task
def retry_failed():
    """
    This task should be scheduled to launch periodically
    """
    waittime = timedelta(seconds=settings.WEBSUBS_VERIFY_WAIT_TIME)
    verify_timeout = Q(**{
        'subscribe_attempt_time__lt': now() - waittime,
        'subscribe_status': 'verifying',
        # TODO: split this setting for error/timeout counters?
        'verify_timeout_count__lt': settings.WEBSUBS_MAX_VERIFY_RETRIES
    })
    connerror = Q(**{
        'subscribe_status': 'connerror',
        'connerror_count__lt': settings.WEBSUBS_MAX_CONNECT_RETRIES
    })
    huberror = Q(**{
        'subscribe_status': 'huberror',
        'huberror_count__lt': settings.WEBSUBS_MAX_HUB_ERROR_RETRIES
    })
    verifyerror = Q(**{
        'subscribe_status': 'verifyerror',
        # TODO: split this setting for error/timeout counters?
        'verifyerror_count__lt': settings.WEBSUBS_MAX_VERIFY_RETRIES
    })

    errors = verify_timeout | connerror | huberror | verifyerror

    # Exclude explicitly unsubscribed
    _filter = errors & Q(unsubscribe_status__isnull=True)

    for ssn in Subscription.objects.filter(_filter):
        subscribe.delay(pk=ssn.pk)


@shared_task
@lock_or_exit('websubsub_{pk}')
def subscribe(*, pk, urlname=None):
    ssn = Subscription.objects.get(pk=pk)

    if ssn.unsubscribe_status is not None:
        logger.warning(f'Subscription {ssn.pk} was explicitly unsubscribed, skipping.')
        return

    #TODO if urlname and ssn.callback_urlname != urlname:

    waittime = timedelta(seconds=settings.WEBSUBS_VERIFY_WAIT_TIME)
    if ssn.subscribe_status == 'verifying' \
       and now() < ssn.subscribe_attempt_time + waittime:
        logger.warning(
            f'Subscription {ssn.pk} was attempted to subscribe recently and'
            f'waiting for verification. Skipping.'
        )
        return

    url = reverse(ssn.callback_urlname, args=[uuid4()])
    ssn.callback_url = join(settings.SITE_URL, url)

    data = {
        'hub.mode': 'subscribe',
        'hub.topic': ssn.topic,
        'hub.callback': ssn.callback_url,
    }
    try:
        # TODO: timeout setting
        rr = post(ssn.hub_url, data, timeout=10)
    except Exception as e:
        ssn.connerror_count += 1
        ssn.subscribe_status = 'connerror'
        ssn.save()
        logger.exception(e)
        left = max(0, settings.WEBSUBS_MAX_CONNECT_RETRIES - ssn.connerror_count)
        logger.error(f'Subscription {ssn.pk} failed to connect to hub. Retries left: {left}')
        return
    else:
        logger.debug('Got hub response')
    finally:
        ssn.subscribe_attempt_time = now()
        ssn.save()

    if rr.status_code != status.HTTP_202_ACCEPTED:
        # TODO: handle specific response codes accordingly
        ssn.subscribe_status = 'huberror'
        ssn.huberror_count += 1
        ssn.save()
        left = max(0, settings.WEBSUBS_MAX_HUB_ERROR_RETRIES - ssn.huberror_count)
        logger.error(f'Subscription {ssn.pk} got hub error {rr.status_code}. Retries left: {left}')
        return

    ssn.subscribe_status = 'verifying'
    ssn.save()


@shared_task(retries=10)
@lock_wait('websubsub_{pk}')
def unsubscribe(*, pk):
    pass  # TODO
