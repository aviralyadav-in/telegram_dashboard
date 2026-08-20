import asyncio

from asgiref.sync import sync_to_async

from django.core.management.base import BaseCommand

from telegram import Bot

from publisher.models import TelegramBot

from publisher.services.user_tracking import (
    handle_member_update,
)


class Command(BaseCommand):

    help = "Listen for Telegram bot updates."

    def handle(self, *args, **options):

        try:
            asyncio.run(
                self.run_listener()
            )

        except KeyboardInterrupt:

            self.stdout.write(
                self.style.WARNING(
                    "Telegram listener stopped."
                )
            )

    async def run_bot(
        self,
        bot_record,
    ):

        bot_id = bot_record.id
        bot_token = bot_record.bot_token
        bot_username = bot_record.username

        bot = Bot(
            token=bot_token
        )

        offset = None

        self.stdout.write(
            self.style.SUCCESS(
                f"Listening: @{bot_username}"
            )
        )

        try:

            # Verify bot connection
            me = await bot.get_me()

            self.stdout.write(
                self.style.SUCCESS(
                    f"Connected: @{me.username}"
                )
            )

            while True:

                try:

                    updates = await bot.get_updates(
                        offset=offset,
                        timeout=30,
                        allowed_updates=[
                            "chat_member",
                            "my_chat_member",
                        ],
                    )

                    for update in updates:

                        offset = update.update_id + 1

                        # Handle chat member updates
                        if update.chat_member:

                            try:

                                await sync_to_async(
                                    handle_member_update
                                )(
                                    bot_record,
                                    update,
                                )

                            except Exception as error:

                                self.stdout.write(
                                    self.style.ERROR(
                                        f"User handling error "
                                        f"for bot {bot_id}: "
                                        f"{error}"
                                    )
                                )

                except asyncio.CancelledError:

                    raise

                except Exception as error:

                    self.stdout.write(
                        self.style.ERROR(
                            f"Bot {bot_id} error: "
                            f"{error}"
                        )
                    )

                    # Wait before retrying
                    await asyncio.sleep(5)

        finally:

            try:
                await bot.shutdown()

            except Exception:
                pass

    async def run_listener(self):

        bots = await sync_to_async(list)(
            TelegramBot.objects.filter(
                status="active"
            )
        )

        if not bots:

            self.stdout.write(
                self.style.WARNING(
                    "No active Telegram bots found."
                )
            )

            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Found {len(bots)} active bot(s)."
            )
        )

        tasks = []

        for bot_record in bots:

            # Create actual asyncio Task.
            # Do NOT append self.run_bot() directly.
            task = asyncio.create_task(
                self.run_bot(
                    bot_record
                )
            )

            tasks.append(task)

        try:

            await asyncio.gather(
                *tasks
            )

        except asyncio.CancelledError:

            self.stdout.write(
                self.style.WARNING(
                    "Listener tasks cancelled."
                )
            )

            for task in tasks:

                if not task.done():

                    task.cancel()

            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

            raise

        finally:

            for task in tasks:

                if not task.done():

                    task.cancel()

            if tasks:

                await asyncio.gather(
                    *tasks,
                    return_exceptions=True,
                )