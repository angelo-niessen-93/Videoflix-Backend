import django_rq
from rq import Retry


def queue_task(queue, function, record_id, timeout, retries):
    return django_rq.get_queue(queue).enqueue(
        function,
        record_id,
        retry=Retry(max=retries),
        job_timeout=timeout,
        failure_ttl=604800,
    )
