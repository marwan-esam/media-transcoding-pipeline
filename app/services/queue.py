import json
import aio_pika
from app.core.config import settings

async def publish_transcode_task(video_id: str, s3_key: str):

  connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)

  async with connection:
    channel = await connection.channel()

    dlx = await channel.declare_exchange(
      "video_dlx",
      aio_pika.ExchangeType.DIRECT,
      durable=True
    )

    dlq = await channel.declare_queue("transcode_dlq", durable=True)

    await dlq.bind(dlx, routing_key="transcode.failed")


    main_exchange = await channel.declare_exchange(
      "video_exchange",
      aio_pika.ExchangeType.DIRECT,
      durable=True
    )

    queue_args = {
      "x-dead-letter-exchange": "video_dlx",
      "x-dead-letter-routing-key": "transcode.failed"
    }

    main_queue = await channel.declare_queue(
      "transcode_queue",
      durable=True,
      arguments=queue_args
    )

    await main_queue.bind(main_exchange, routing_key="task.transcode")

    message_payload = {
      "video_id": str(video_id),
      "s3_key": s3_key
    }

    message = aio_pika.Message(
      body=json.dumps(message_payload).encode(),
      delivery_mode=aio_pika.DeliveryMode.PERSISTENT
    )

    await main_exchange.publish(
      message,
      routing_key="task.transcode"
    )