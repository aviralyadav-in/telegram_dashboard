import asyncio

from asgiref.sync import sync_to_async

from django.core.management.base import BaseCommand

from telegram import Bot

from publisher.models import TelegramBot

from publisher.services.user_tracking import (
    handle_member_update,
)

from publisher.services.direct_messages import (
    handle_private_message,
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

    # ========================================================
    # RUN ONE BOT
    # ========================================================

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
                f"Listening: @{bot_username or 'unknown'}"
            )
        )

        try:

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
                            "message",
                            "chat_member",
                            "my_chat_member",
                        ],
                    )

                    for update in updates:

                        offset = (
                            update.update_id + 1
                        )

                        # =====================================
                        # PRIVATE MESSAGE
                        # =====================================

                        if update.message:

                            try:

                                await sync_to_async(
                                    handle_private_message
                                )(
                                    bot_record,
                                    update,
                                )

                            except Exception as error:

                                self.stdout.write(
                                    self.style.ERROR(
                                        f"Private message error "
                                        f"for bot {bot_id}: "
                                        f"{error}"
                                    )
                                )

                        # =====================================
                        # CHAT MEMBER
                        # =====================================

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

                        # =====================================
                        # BOT CHAT MEMBER
                        # =====================================

                        if update.my_chat_member:

                            self.stdout.write(
                                self.style.SUCCESS(
                                    f"Bot membership update "
                                    f"received for bot "
                                    f"{bot_id}"
                                )
                            )

                            await self.handle_bot_chat_update(
                                bot_record,
                                update,
                            )

                except asyncio.CancelledError:

                    raise

                except Exception as error:

                    self.stdout.write(
                        self.style.ERROR(
                            f"Bot {bot_id} error: {error}"
                        )
                    )

                    await asyncio.sleep(5)

        finally:

            try:

                await bot.shutdown()

            except Exception:

                pass

    # ========================================================
    # BOT MEMBERSHIP UPDATE
    # ========================================================

    async def handle_bot_chat_update(
        self,
        bot_record,
        update,
    ):

        chat_member = update.my_chat_member

        if not chat_member:
            return

        chat = chat_member.chat

        new_status = (
            chat_member
            .new_chat_member
            .status
        )

        active_statuses = {
            "member",
            "administrator",
        }

        inactive_statuses = {
            "left",
            "kicked",
        }

        if new_status in active_statuses:

            await sync_to_async(
                self.mark_destination_active
            )(
                bot_record,
                chat,
            )

        elif new_status in inactive_statuses:

            await sync_to_async(
                self.mark_destination_inactive
            )(
                bot_record,
                chat,
            )

    # ========================================================
    # MARK ACTIVE
    # ========================================================

    def mark_destination_active(
        self,
        bot_record,
        chat,
    ):

        from publisher.models import PublishedChannel

        PublishedChannel.objects.filter(
            bot=bot_record,
            chat_id=chat.id,
        ).update(
            status="active"
        )

    # ========================================================
    # MARK INACTIVE
    # ========================================================

    def mark_destination_inactive(
        self,
        bot_record,
        chat,
    ):

        from publisher.models import PublishedChannel

        PublishedChannel.objects.filter(
            bot=bot_record,
            chat_id=chat.id,
        ).update(
            status="inactive"
        )

    # ========================================================
    # RUN ALL ACTIVE BOTS
    # ========================================================

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