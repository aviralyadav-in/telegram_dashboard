import asyncio

from asgiref.sync import sync_to_async

from django.core.management.base import BaseCommand

from telegram import Bot
from telegram.request import HTTPXRequest

from publisher.models import TelegramBot

from publisher.services.user_tracking import (
    handle_member_update,
)

from publisher.services.direct_messages import (
    handle_private_message,
    handle_callback_query,
)


class Command(BaseCommand):

    help = "Listen for Telegram bot updates."

    # ========================================================
    # HANDLE
    # ========================================================

    def handle(
        self,
        *args,
        **options,
    ):

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

        bot_token = (
            bot_record.bot_token
        )

        bot_username = (
            bot_record.username
        )

        # ====================================================
        # TELEGRAM REQUEST TIMEOUTS
        # ====================================================

        request = HTTPXRequest(
            connect_timeout=30.0,
            read_timeout=60.0,
            write_timeout=60.0,
            pool_timeout=30.0,
        )

        bot = Bot(
            token=bot_token,
            request=request,
        )

        offset = None

        self.stdout.write(
            self.style.SUCCESS(
                f"Listening: @{bot_username}"
            )
        )

        try:

            # =================================================
            # VERIFY BOT
            # =================================================

            me = await bot.get_me()

            self.stdout.write(
                self.style.SUCCESS(
                    f"Connected: @{me.username} "
                    f"(ID: {me.id})"
                )
            )

            # =================================================
            # POLLING
            # =================================================

            while True:

                try:

                    updates = await bot.get_updates(
                        offset=offset,
                        timeout=30,

                        allowed_updates=[
                            "message",
                            "callback_query",
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

                                await handle_private_message(
                                    bot_record,
                                    update,
                                    bot,
                                )

                            except Exception as error:

                                self.stdout.write(
                                    self.style.ERROR(
                                        "Message error "
                                        f"for bot {bot_id}: "
                                        f"{repr(error)}"
                                    )
                                )

                        # =====================================
                        # CALLBACK QUERY
                        # =====================================

                        elif update.callback_query:

                            try:

                                await handle_callback_query(
                                    bot,
                                    update,
                                )

                            except Exception as error:

                                self.stdout.write(
                                    self.style.ERROR(
                                        "Callback error "
                                        f"for bot {bot_id}: "
                                        f"{repr(error)}"
                                    )
                                )

                        # =====================================
                        # CHAT MEMBER
                        # =====================================

                        elif update.chat_member:

                            try:

                                # IMPORTANT:
                                #
                                # handle_member_update is now
                                # an ASYNC function.
                                #
                                # DO NOT wrap it in
                                # sync_to_async().
                                #
                                await handle_member_update(
                                    bot_record,
                                    update,
                                    bot,
                                )

                            except Exception as error:

                                self.stdout.write(
                                    self.style.ERROR(
                                        "Member handling error "
                                        f"for bot {bot_id}: "
                                        f"{repr(error)}"
                                    )
                                )

                        # =====================================
                        # BOT'S OWN MEMBERSHIP
                        # =====================================

                        elif update.my_chat_member:

                            # This update is about the bot
                            # itself joining/leaving a chat.
                            #
                            # It is NOT treated as a user join.

                            continue

                except asyncio.CancelledError:

                    raise

                except Exception as error:

                    self.stdout.write(
                        self.style.ERROR(
                            f"Bot {bot_id} polling error: "
                            f"{repr(error)}"
                        )
                    )

                    await asyncio.sleep(5)

        finally:

            try:

                await bot.shutdown()

            except Exception:

                pass

    # ========================================================
    # RUN ALL ACTIVE BOTS
    # ========================================================

    async def run_listener(
        self,
    ):

        bots = await sync_to_async(
            list
        )(
            TelegramBot.objects
            .filter(
                status="active"
            )
            .order_by("id")
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

            tasks.append(
                asyncio.create_task(
                    self.run_bot(
                        bot_record
                    )
                )
            )

        try:

            await asyncio.gather(
                *tasks
            )

        except asyncio.CancelledError:

            for task in tasks:

                task.cancel()

            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

            raise