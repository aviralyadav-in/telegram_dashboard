from datetime import timedelta
import asyncio
import traceback

from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.utils import timezone

from telegram import (
    Bot,
    ReplyKeyboardMarkup,
)

from deals.models import Deal, Category

from publisher.services.user_tracking import (
    get_or_create_telegram_user,
)


# ============================================================
# KEYBOARDS
# ============================================================

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🔎 Find Deals"],
        ["🆕 Latest Deals"],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)

CATEGORY_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["📱 Electronics"],
        ["🛒 Grocery"],
        ["👕 Fashion"],
        ["🏠 Home"],
        ["📦 All Categories"],
        ["⬅️ Back"],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)

PRICE_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["💰 Under ₹300"],
        ["💰 ₹300 - ₹500"],
        ["💰 ₹500 - ₹700"],
        ["💰 ₹700 - ₹1000"],
        ["💰 Above ₹1000"],
        ["💰 Any Price"],
        ["⬅️ Back"],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)

DATE_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["📅 Today"],
        ["📅 Last 7 Days"],
        ["📅 Last 30 Days"],
        ["📅 Any Date"],
        ["⬅️ Back"],
    ],
    resize_keyboard=True,
    one_time_keyboard=False,
)


# ============================================================
# SEND MESSAGE
# ============================================================

async def send_bot_message(
    bot,
    chat_id,
    text,
    keyboard=None,
):
    return await bot.send_message(
        chat_id=chat_id,
        text=text,
        reply_markup=keyboard,
    )


# ============================================================
# MAIN MENU
# ============================================================

async def send_main_menu(
    bot,
    chat_id,
    name=None,
):
    name = name or "there"

    text = (
        f"👋 Hi {name}!\n\n"
        "Welcome to MyDeals Deal Finder.\n\n"
        "You can browse deals directly here without "
        "opening any website or UI.\n\n"
        "👇 Choose an option:"
    )

    await send_bot_message(
        bot,
        chat_id,
        text,
        MAIN_KEYBOARD,
    )


# ============================================================
# CATEGORY MENU
# ============================================================

async def send_category_menu(
    bot,
    chat_id,
):
    await send_bot_message(
        bot,
        chat_id,
        (
            "🔎 Find Deals\n\n"
            "First, choose the category you want:"
        ),
        CATEGORY_KEYBOARD,
    )


# ============================================================
# PRICE MENU
# ============================================================

async def send_price_menu(
    bot,
    chat_id,
    category,
):
    await send_bot_message(
        bot,
        chat_id,
        (
            f"✅ Category: {category}\n\n"
            "Now choose your price range:"
        ),
        PRICE_KEYBOARD,
    )


# ============================================================
# DATE MENU
# ============================================================

async def send_date_menu(
    bot,
    chat_id,
    category,
    price_label,
):
    await send_bot_message(
        bot,
        chat_id,
        (
            f"✅ Category: {category}\n"
            f"✅ Price: {price_label}\n\n"
            "Finally, choose the date range:"
        ),
        DATE_KEYBOARD,
    )


# ============================================================
# CATEGORY MATCH
# ============================================================

def category_matches(
    deal,
    category_name,
):
    if category_name == "All Categories":
        return True

    content = (
        f"{deal.content or ''} "
        f"{deal.product_link or ''}"
    ).lower()

    try:
        category = (
            Category.objects
            .filter(
                name__iexact=category_name,
                status="active",
            )
            .first()
        )

        if category:
            keywords = category.get_keywords_list()

            if keywords:
                return any(
                    keyword in content
                    for keyword in keywords
                )

            return category_name.lower() in content

    except Exception as error:
        print(
            "❌ CATEGORY MATCH ERROR:",
            repr(error),
        )
        traceback.print_exc()

    return category_name.lower() in content


# ============================================================
# PRICE FILTER
# ============================================================

def apply_price_filter(
    queryset,
    price_label,
):
    if price_label == "Any Price":
        return queryset

    if price_label == "Under ₹300":
        return queryset.filter(
            price__lt=300
        )

    if price_label == "₹300 - ₹500":
        return queryset.filter(
            price__gte=300,
            price__lte=500,
        )

    if price_label == "₹500 - ₹700":
        return queryset.filter(
            price__gte=500,
            price__lte=700,
        )

    if price_label == "₹700 - ₹1000":
        return queryset.filter(
            price__gte=700,
            price__lte=1000,
        )

    if price_label == "Above ₹1000":
        return queryset.filter(
            price__gt=1000
        )

    return queryset


# ============================================================
# DATE FILTER
# ============================================================

def apply_date_filter(
    queryset,
    date_label,
):
    now = timezone.now()

    if date_label == "Today":
        start = now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        return queryset.filter(
            date__gte=start
        )

    if date_label == "Last 7 Days":
        return queryset.filter(
            date__gte=now - timedelta(days=7)
        )

    if date_label == "Last 30 Days":
        return queryset.filter(
            date__gte=now - timedelta(days=30)
        )

    return queryset


# ============================================================
# FIND MATCHING DEALS
#
# NORMAL SYNC FUNCTION
# Do NOT wrap this function with sync_to_async here.
# ============================================================

def find_matching_deals(
    category,
    price_label,
    date_label,
):
    print("\n========================================")
    print("🔎 FIND DEALS START")
    print("Category:", category)
    print("Price:", price_label)
    print("Date:", date_label)
    print("========================================")

    try:
        deals = (
            Deal.objects
            .filter(
                status__in=[
                    "new",
                    "processed",
                    "published",
                ]
            )
            .order_by(
                "-date",
                "-id",
            )
        )

        deals = apply_price_filter(
            deals,
            price_label,
        )

        deals = apply_date_filter(
            deals,
            date_label,
        )

        # Evaluate queryset inside the worker thread.
        deals = list(deals[:200])

        print(
            "STEP 1 - Deals loaded:",
            len(deals),
        )

        results = []

        for deal in deals:
            try:
                if category_matches(
                    deal,
                    category,
                ):
                    results.append(deal)

            except Exception as error:
                print(
                    f"❌ Category error for Deal #{deal.id}:",
                    repr(error),
                )

                traceback.print_exc()

            if len(results) >= 20:
                break

        print(
            "STEP 2 - Matching deals:",
            len(results),
        )

        print("========================================")
        print("🔎 FIND DEALS END")
        print("========================================")

        return results

    except Exception as error:
        print(
            "❌ FIND DEALS DATABASE ERROR:",
            repr(error),
        )

        traceback.print_exc()

        raise


# ============================================================
# FORMAT DEAL
# ============================================================

def format_deal(
    deal,
):
    text = (
        f"🛍️ <b>Deal #{deal.id}</b>\n\n"
        f"{deal.content or 'Deal available'}\n\n"
    )

    if deal.price is not None:
        text += (
            f"💰 Price: ₹{deal.price}\n"
        )

    if deal.rating is not None:
        text += (
            f"⭐ Rating: {deal.rating}\n"
        )

    if deal.date:
        text += (
            f"📅 {deal.date.strftime('%d %b %Y')}\n"
        )

    if deal.product_link:
        text += (
            f'\n🔗 <a href="{deal.product_link}">'
            "View Deal</a>"
        )

    return text


# ============================================================
# SEND FILTERED DEALS
# ============================================================

async def send_filtered_deals(
    bot,
    chat_id,
    category,
    price_label,
    date_label,
):
    try:
        print("\n########################################")
        print("FILTER REQUEST")
        print("CATEGORY =", category)
        print("PRICE =", price_label)
        print("DATE =", date_label)
        print("########################################")

        # IMPORTANT:
        # sync_to_async is used ONLY HERE.
        deals = await sync_to_async(
            find_matching_deals,
            thread_sensitive=False,
        )(
            category,
            price_label,
            date_label,
        )

        print(
            "FILTER RESULT:",
            len(deals),
            "deals",
        )

    except Exception as error:
        print("\n########################################")
        print("❌ DEAL FETCH ERROR")
        print(
            "ERROR:",
            type(error).__name__,
            str(error),
        )
        print("########################################")

        traceback.print_exc()

        await send_bot_message(
            bot,
            chat_id,
            (
                "⚠️ DEAL FETCH ERROR\n\n"
                f"{type(error).__name__}: {error}\n\n"
                "Please check the Django terminal."
            ),
            MAIN_KEYBOARD,
        )

        return

    if not deals:
        await send_bot_message(
            bot,
            chat_id,
            (
                "😔 No deals found for your "
                "selected filters.\n\n"
                f"📂 Category: {category}\n"
                f"💰 Price: {price_label}\n"
                f"📅 Date: {date_label}\n\n"
                "Try another combination."
            ),
            MAIN_KEYBOARD,
        )

        return

    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"🎯 Found {len(deals)} matching deal(s)!\n\n"
            f"📂 {category}\n"
            f"💰 {price_label}\n"
            f"📅 {date_label}"
        ),
        reply_markup=MAIN_KEYBOARD,
    )

    for deal in deals:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=format_deal(deal),
                parse_mode="HTML",
                disable_web_page_preview=False,
            )

        except Exception as error:
            print(
                f"❌ Failed sending Deal #{deal.id}:",
                repr(error),
            )

            traceback.print_exc()


# ============================================================
# GET LATEST DEALS
#
# NORMAL SYNC FUNCTION
# ============================================================

def get_latest_deals():
    print("🔎 Loading latest deals...")

    deals = list(
        Deal.objects
        .filter(
            status__in=[
                "new",
                "processed",
                "published",
            ]
        )
        .order_by(
            "-date",
            "-id",
        )[:10]
    )

    print(
        "Latest deals loaded:",
        len(deals),
    )

    return deals


# ============================================================
# SEND LATEST DEALS
# ============================================================

async def send_latest_deals(
    bot,
    chat_id,
):
    try:
        # IMPORTANT:
        # sync_to_async is used ONLY HERE.
        deals = await sync_to_async(
            get_latest_deals,
            thread_sensitive=False,
        )()

    except Exception as error:
        print(
            "❌ LATEST DEAL ERROR:",
            repr(error),
        )

        traceback.print_exc()

        await send_bot_message(
            bot,
            chat_id,
            (
                "⚠️ Latest deals fetch karte time "
                "problem aa gayi.\n\n"
                f"{type(error).__name__}: {error}"
            ),
            MAIN_KEYBOARD,
        )

        return

    if not deals:
        await send_bot_message(
            bot,
            chat_id,
            "😔 No deals available right now.",
            MAIN_KEYBOARD,
        )

        return

    await send_bot_message(
        bot,
        chat_id,
        "🆕 Here are the latest deals:",
        MAIN_KEYBOARD,
    )

    for deal in deals:
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=format_deal(deal),
                parse_mode="HTML",
                disable_web_page_preview=False,
            )

        except Exception as error:
            print(
                f"❌ Latest Deal #{deal.id} send error:",
                repr(error),
            )

            traceback.print_exc()


# ============================================================
# PRIVATE MESSAGE HANDLER
# ============================================================

def handle_private_message(
    bot_record,
    update,
):
    message = update.message

    if not message:
        return

    if not message.from_user:
        return

    telegram_user = message.from_user

    user, created = get_or_create_telegram_user(
        telegram_user
    )

    text = (
        message.text or ""
    ).strip()

    # ========================================================
    # START
    # ========================================================

    if text.startswith("/start"):

        async def send():
            bot = Bot(
                token=bot_record.bot_token
            )

            try:
                await send_main_menu(
                    bot,
                    message.chat_id,
                    telegram_user.first_name,
                )

            finally:
                await bot.shutdown()

        asyncio.run(send())

        return

    # ========================================================
    # FIND DEALS
    # ========================================================

    if text == "🔎 Find Deals":

        async def send():
            bot = Bot(
                token=bot_record.bot_token
            )

            try:
                await send_category_menu(
                    bot,
                    message.chat_id,
                )

            finally:
                await bot.shutdown()

        asyncio.run(send())

        return

    # ========================================================
    # LATEST DEALS
    # ========================================================

    if text == "🆕 Latest Deals":

        async def send():
            bot = Bot(
                token=bot_record.bot_token
            )

            try:
                await send_latest_deals(
                    bot,
                    message.chat_id,
                )

            finally:
                await bot.shutdown()

        asyncio.run(send())

        return

    # ========================================================
    # CATEGORY
    # ========================================================

    category_map = {
        "📱 Electronics": "Electronics",
        "🛒 Grocery": "Grocery",
        "👕 Fashion": "Fashion",
        "🏠 Home": "Home",
        "📦 All Categories": "All Categories",
    }

    if text in category_map:

        category = category_map[text]

        cache.set(
            f"deal_filter_category_{user.user_id}",
            category,
            timeout=1800,
        )

        async def send():
            bot = Bot(
                token=bot_record.bot_token
            )

            try:
                await send_price_menu(
                    bot,
                    message.chat_id,
                    category,
                )

            finally:
                await bot.shutdown()

        asyncio.run(send())

        return

    # ========================================================
    # PRICE
    # ========================================================

    price_options = {
        "💰 Under ₹300": "Under ₹300",
        "💰 ₹300 - ₹500": "₹300 - ₹500",
        "💰 ₹500 - ₹700": "₹500 - ₹700",
        "💰 ₹700 - ₹1000": "₹700 - ₹1000",
        "💰 Above ₹1000": "Above ₹1000",
        "💰 Any Price": "Any Price",
    }

    if text in price_options:

        category = cache.get(
            f"deal_filter_category_{user.user_id}"
        )

        if not category:
            print(
                "❌ Category missing from cache"
            )
            return

        price_label = price_options[text]

        cache.set(
            f"deal_filter_price_{user.user_id}",
            price_label,
            timeout=1800,
        )

        async def send():
            bot = Bot(
                token=bot_record.bot_token
            )

            try:
                await send_date_menu(
                    bot,
                    message.chat_id,
                    category,
                    price_label,
                )

            finally:
                await bot.shutdown()

        asyncio.run(send())

        return

    # ========================================================
    # DATE
    # ========================================================

    date_options = {
        "📅 Today": "Today",
        "📅 Last 7 Days": "Last 7 Days",
        "📅 Last 30 Days": "Last 30 Days",
        "📅 Any Date": "Any Date",
    }

    if text in date_options:

        category = cache.get(
            f"deal_filter_category_{user.user_id}"
        )

        price_label = cache.get(
            f"deal_filter_price_{user.user_id}"
        )

        if not category:
            print(
                "❌ Category missing before date filter"
            )
            return

        if not price_label:
            print(
                "❌ Price missing before date filter"
            )
            return

        date_label = date_options[text]

        async def send():
            bot = Bot(
                token=bot_record.bot_token
            )

            try:
                await send_filtered_deals(
                    bot,
                    message.chat_id,
                    category,
                    price_label,
                    date_label,
                )

            finally:
                await bot.shutdown()

        asyncio.run(send())

        return

    # ========================================================
    # BACK
    # ========================================================

    if text == "⬅️ Back":

        async def send():
            bot = Bot(
                token=bot_record.bot_token
            )

            try:
                await send_main_menu(
                    bot,
                    message.chat_id,
                    telegram_user.first_name,
                )

            finally:
                await bot.shutdown()

        asyncio.run(send())

        return
