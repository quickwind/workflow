from __future__ import annotations

import logging

from .models import UserTask

logger = logging.getLogger(__name__)


def send_user_task_notification(user_task: UserTask) -> None:
    logger.info(
        "Stub user task notification: task_id=%s workflow_instance_id=%s name=%s",
        user_task.task_id,
        user_task.workflow_instance_id,
        user_task.name,
    )
