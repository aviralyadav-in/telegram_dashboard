from datetime import datetime, timedelta
import asyncio
import re
import traceback
from html import escape

from asgiref.sync import sync_to_async
from django.core.cache import cache
from django.utils import timezone

from telegram import Bot, ReplyKeyboardMarkup

from deals.models import Deal, Category

from publisher.services.user_tracking import (
    get_or_create_telegram_user,
)


# ============================================================
# MAIN KEYBOARD
# ============================================================

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["🔎 Find Deals"],
        ["🆕 Latest Deals"],
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
# CATEGORY INPUT
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
            "Enter the category you want.\n\n"
            "Examples:\n"
            "• Electronics\n"
            "• Grocery\n"
            "• Fashion\n"
            "• Home\n"
            "• All Categories\n\n"
            "You can type the category name."
        ),
        MAIN_KEYBOARD,
    )


# ============================================================
# PRICE INPUT
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
            "Now enter your price range.\n\n"
            "Examples:\n"
            "• 500-700\n"
            "• 700-1000\n"
            "• under 300\n"
            "• above 1000\n"
            "• any"
        ),
        MAIN_KEYBOARD,
    )


# ============================================================
# DATE INPUT
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
            "Finally, enter the date range.\n\n"
            "Examples:\n"
            "• today\n"
            "• 7   → last 7 days\n"
            "• 30  → last 30 days\n"
            "• 25-08-2026 → particular date\n"
            "• any"
        ),
        MAIN_KEYBOARD,
    )


# ============================================================
# SEARCH AGAIN
# ============================================================

async def send_search_again_prompt(
    bot,
    chat_id,
):
    await send_bot_message(
        bot,
        chat_id,
        (
            "🔎 Start another search.\n\n"
            "Enter the category you want.\n\n"
            "Examples:\n"
            "• Electronics\n"
            "• Grocery\n"
            "• Fashion\n"
            "• Home\n"
            "• All Categories"
        ),
        MAIN_KEYBOARD,
    )


# ============================================================
# CATEGORY RESOLUTION
# ============================================================

def resolve_category(
    user_input,
):
    """
    Converts user input into the actual Category name.

    Examples:
        Electronics -> Electronics & Gadgets
        Grocery -> Grocery
        Home -> Home & Kitchen
        Fashion -> Fashion
        all -> All Categories
    """

    value = (
        user_input or ""
    ).strip().lower()

    if not value:
        return None

    # --------------------------------------------------------
    # ALL CATEGORIES
    # --------------------------------------------------------

    if value in [
        "all",
        "all categories",
        "all category",
        "any",
        "*",
    ]:
        return "All Categories"

    # --------------------------------------------------------
    # EXACT DATABASE CATEGORY
    # --------------------------------------------------------

    category = (
        Category.objects
        .filter(
            name__iexact=user_input.strip(),
            status="active",
        )
        .first()
    )

    if category:
        return category.name

    # --------------------------------------------------------
    # COMMON ALIASES
    # --------------------------------------------------------

    aliases = {
        "electronics": "Electronics & Gadgets",
        "electronic": "Electronics & Gadgets",
        "gadgets": "Electronics & Gadgets",

        "grocery": "Grocery",
        "groceries": "Grocery",

        "fashion": "Fashion",
        "clothes": "Fashion",
        "clothing": "Fashion",

        "home": "Home & Kitchen",
        "kitchen": "Home & Kitchen",

        "beauty": "Beauty & Personal Care",
        "personal care": "Beauty & Personal Care",

        "fitness": "Fitness & Sports",
        "sports": "Fitness & Sports",

        "kids": "Kids & Toys",
        "toys": "Kids & Toys",
    }

    category_name = aliases.get(
        value
    )

    if category_name:

        category = (
            Category.objects
            .filter(
                name__iexact=category_name,
                status="active",
            )
            .first()
        )

        if category:
            return category.name

    # --------------------------------------------------------
    # PARTIAL DATABASE NAME
    # --------------------------------------------------------

    categories = (
        Category.objects
        .filter(status="active")
    )

    for category in categories:

        db_name = category.name.lower()

        if (
            value in db_name
            or db_name in value
        ):
            return category.name

    return None


# ============================================================
# CATEGORY MATCH
# ============================================================

def category_matches(
    deal,
    category_name,
):
    """
    Strict keyword based category matching.
    """

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

            keywords = (
                category.get_keywords_list()
            )

            if keywords:

                return any(
                    keyword in content
                    for keyword in keywords
                )

            return (
                category_name.lower()
                in content
            )

    except Exception as error:

        print(
            "❌ CATEGORY MATCH ERROR:",
            repr(error),
        )

        traceback.print_exc()

    return (
        category_name.lower()
        in content
    )


# ============================================================
# PRICE INPUT PARSER
# ============================================================

def parse_price_input(
    user_input,
):
    """
    Supported:

        500-700
        500 - 700
        under 300
        below 300
        above 1000
        over 1000
        any
    """

    value = (
        user_input or ""
    ).strip().lower()

    value = value.replace(
        "₹",
        "",
    )

    value = value.replace(
        ",",
        "",
    )

    # --------------------------------------------------------
    # ANY
    # --------------------------------------------------------

    if value in [
        "any",
        "any price",
        "all",
        "no filter",
    ]:

        return {
            "type": "any",
            "label": "Any Price",
        }

    # --------------------------------------------------------
    # UNDER
    # --------------------------------------------------------

    match = re.match(
        r"^(under|below|less than)\s*(\d+(?:\.\d+)?)$",
        value,
    )

    if match:

        amount = float(
            match.group(2)
        )

        return {
            "type": "under",
            "max": amount,
            "label": f"Under ₹{amount:g}",
        }

    # --------------------------------------------------------
    # ABOVE
    # --------------------------------------------------------

    match = re.match(
        r"^(above|over|more than)\s*(\d+(?:\.\d+)?)$",
        value,
    )

    if match:

        amount = float(
            match.group(2)
        )

        return {
            "type": "above",
            "min": amount,
            "label": f"Above ₹{amount:g}",
        }

    # --------------------------------------------------------
    # RANGE
    # --------------------------------------------------------

    match = re.match(
        r"^(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)$",
        value,
    )

    if match:

        minimum = float(
            match.group(1)
        )

        maximum = float(
            match.group(2)
        )

        if minimum > maximum:
            minimum, maximum = (
                maximum,
                minimum,
            )

        return {
            "type": "range",
            "min": minimum,
            "max": maximum,
            "label": (
                f"₹{minimum:g} - ₹{maximum:g}"
            ),
        }

    # --------------------------------------------------------
    # SINGLE EXACT PRICE
    # --------------------------------------------------------

    if re.match(
        r"^\d+(?:\.\d+)?$",
        value,
    ):

        amount = float(value)

        return {
            "type": "single",
            "min": amount,
            "max": amount,
            "label": f"₹{amount:g}",
        }

    return None


# ============================================================
# PRICE FILTER
# ============================================================

def apply_price_filter(
    queryset,
    price_data,
):

    if not price_data:
        return queryset

    price_type = price_data.get(
        "type"
    )

    if price_type == "any":
        return queryset

    if price_type == "under":
        return queryset.filter(
            price__lt=price_data["max"]
        )

    if price_type == "above":
        return queryset.filter(
            price__gt=price_data["min"]
        )

    if price_type == "range":
        return queryset.filter(
            price__gte=price_data["min"],
            price__lte=price_data["max"],
        )

    if price_type == "single":
        return queryset.filter(
            price=price_data["min"]
        )

    return queryset


# ============================================================
# DATE INPUT PARSER
# ============================================================

def parse_date_input(
    user_input,
):
    """
    Supported:

        today
        7
        30
        any
        25-08-2026
        25/08/2026
        25.08.2026
    """

    value = (
        user_input or ""
    ).strip().lower()

    # --------------------------------------------------------
    # ANY
    # --------------------------------------------------------

    if value in [
        "any",
        "any date",
        "all",
        "no filter",
    ]:

        return {
            "type": "any",
            "label": "Any Date",
        }

    # --------------------------------------------------------
    # TODAY
    # --------------------------------------------------------

    if value in [
        "today",
        "todays",
        "today's",
    ]:

        return {
            "type": "today",
            "label": "Today",
        }

    # --------------------------------------------------------
    # LAST N DAYS
    # --------------------------------------------------------

    if re.match(
        r"^\d+$",
        value,
    ):

        days = int(value)

        if days <= 0:
            return None

        if days > 3650:
            return None

        return {
            "type": "days",
            "days": days,
            "label": f"Last {days} Days",
        }

    # --------------------------------------------------------
    # PARTICULAR DATE
    # --------------------------------------------------------

    for date_format in [
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d.%m.%Y",
    ]:

        try:

            selected_date = datetime.strptime(
                value,
                date_format,
            ).date()

            return {
                "type": "specific",
                "date": selected_date,
                "label": selected_date.strftime(
                    "%d-%m-%Y"
                ),
            }

        except ValueError:
            continue

    return None


# ============================================================
# DATE FILTER
# ============================================================

def apply_date_filter(
    queryset,
    date_data,
):

    if not date_data:
        return queryset

    date_type = date_data.get(
        "type"
    )

    # --------------------------------------------------------
    # ANY DATE
    # --------------------------------------------------------

    if date_type == "any":
        return queryset

    now = timezone.now()

    # --------------------------------------------------------
    # TODAY
    # --------------------------------------------------------

    if date_type == "today":

        start = now.replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

        end = (
            start
            + timedelta(days=1)
        )

        return queryset.filter(
            date__gte=start,
            date__lt=end,
        )

    # --------------------------------------------------------
    # LAST N DAYS
    # --------------------------------------------------------

    if date_type == "days":

        return queryset.filter(
            date__gte=(
                now
                - timedelta(
                    days=date_data["days"]
                )
            )
        )

    # --------------------------------------------------------
    # PARTICULAR DATE
    # --------------------------------------------------------

    if date_type == "specific":

        selected_date = date_data["date"]

        start = timezone.make_aware(
            datetime.combine(
                selected_date,
                datetime.min.time(),
            )
        )

        end = (
            start
            + timedelta(days=1)
        )

        return queryset.filter(
            date__gte=start,
            date__lt=end,
        )

    return queryset


# ============================================================
# FIND MATCHING DEALS
# ============================================================

def find_matching_deals(
    category,
    price_data,
    date_data,
):

    print("\n========================================")
    print("🔎 FIND DEALS START")
    print("Category:", category)
    print("Price:", price_data)
    print("Date:", date_data)
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

        # ----------------------------------------------------
        # PRICE
        # ----------------------------------------------------

        deals = apply_price_filter(
            deals,
            price_data,
        )

        # ----------------------------------------------------
        # DATE
        # ----------------------------------------------------

        deals = apply_date_filter(
            deals,
            date_data,
        )

        # ----------------------------------------------------
        # LOAD DATABASE RECORDS
        # ----------------------------------------------------

        deals = list(
            deals[:200]
        )

        print(
            "STEP 1 - Deals loaded:",
            len(deals),
        )

        # ----------------------------------------------------
        # CATEGORY
        # ----------------------------------------------------

        results = []

        for deal in deals:

            try:

                if category_matches(
                    deal,
                    category,
                ):

                    results.append(
                        deal
                    )

            except Exception as error:

                print(
                    f"❌ Category error "
                    f"for Deal #{deal.id}:",
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
    """
    Creates HTML-safe Telegram message.
    """

    content = escape(
        deal.content or "Deal available"
    )

    text = (
        f"🛍️ <b>Deal #{deal.id}</b>\n\n"
        f"{content}\n\n"
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
            f"📅 "
            f"{deal.date.strftime('%d %b %Y')}\n"
        )

    if deal.channel:

        text += (
            f"📢 Source: "
            f"{escape(str(deal.channel))}\n"
        )

    if deal.product_link:

        safe_link = escape(
            str(deal.product_link),
            quote=True,
        )

        text += (
            f'\n🔗 <a href="{safe_link}">'
            "View Deal</a>"
        )

    return text


# ============================================================
# SPLIT LONG TELEGRAM MESSAGE
# ============================================================

def split_telegram_message(
    text,
    max_length=3500,
):
    """
    Telegram has a finite message size.

    Long scraped deals are split into multiple messages
    instead of being rejected.
    """

    if len(text) <= max_length:
        return [text]

    chunks = []

    current = ""

    # Prefer splitting on newlines.
    lines = text.split("\n")

    for line in lines:

        # ----------------------------------------------------
        # A single line is itself too long
        # ----------------------------------------------------

        if len(line) > max_length:

            if current:

                chunks.append(
                    current.rstrip()
                )

                current = ""

            start = 0

            while start < len(line):

                end = (
                    start
                    + max_length
                )

                chunks.append(
                    line[start:end]
                )

                start = end

            continue

        # ----------------------------------------------------
        # Normal line
        # ----------------------------------------------------

        candidate = (
            f"{current}\n{line}"
            if current
            else line
        )

        if len(candidate) <= max_length:

            current = candidate

        else:

            if current:

                chunks.append(
                    current.rstrip()
                )

            current = line

    if current:

        chunks.append(
            current.rstrip()
        )

    return chunks


# ============================================================
# SEND FILTERED DEALS
# ============================================================

async def send_filtered_deals(
    bot,
    chat_id,
    category,
    price_data,
    date_data,
    user_cache_key,
):

    try:

        print("\n########################################")
        print("FILTER REQUEST")
        print(
            "CATEGORY =",
            category,
        )
        print(
            "PRICE =",
            price_data,
        )
        print(
            "DATE =",
            date_data,
        )
        print("########################################")

        # IMPORTANT:
        # Django sync ORM runs only at this boundary.
        deals = await sync_to_async(
            find_matching_deals,
            thread_sensitive=False,
        )(
            category,
            price_data,
            date_data,
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

        # Allow another search.
        cache.set(
            user_cache_key,
            {
                "step": "category",
            },
            timeout=1800,
        )

        await send_bot_message(
            bot,
            chat_id,
            (
                "⚠️ Sorry, deals fetch karte time "
                "problem aa gayi.\n\n"
                "Let's try another search."
            ),
            MAIN_KEYBOARD,
        )

        await send_search_again_prompt(
            bot,
            chat_id,
        )

        return

    # ========================================================
    # NO RESULTS
    # ========================================================

    if not deals:

        cache.set(
            user_cache_key,
            {
                "step": "category",
            },
            timeout=1800,
        )

        await send_bot_message(
            bot,
            chat_id,
            (
                "😔 No deals found for your "
                "selected filters.\n\n"
                f"📂 Category: {category}\n"
                f"💰 Price: {price_data['label']}\n"
                f"📅 Date: {date_data['label']}"
            ),
            MAIN_KEYBOARD,
        )

        await send_search_again_prompt(
            bot,
            chat_id,
        )

        return

    # ========================================================
    # RESULTS HEADER
    # ========================================================

    # Reset state so next message can start a new search.
    cache.set(
        user_cache_key,
        {
            "step": "category",
        },
        timeout=1800,
    )

    await bot.send_message(
        chat_id=chat_id,
        text=(
            f"🎯 Found {len(deals)} matching deal(s)!\n\n"
            f"📂 {category}\n"
            f"💰 {price_data['label']}\n"
            f"📅 {date_data['label']}"
        ),
        reply_markup=MAIN_KEYBOARD,
    )

    # ========================================================
    # SEND EACH DEAL
    # ========================================================

    for deal in deals:

        try:

            formatted_text = format_deal(
                deal
            )

            chunks = split_telegram_message(
                formatted_text
            )

            for index, chunk in enumerate(
                chunks
            ):

                try:

                    await bot.send_message(
                        chat_id=chat_id,
                        text=chunk,
                        parse_mode="HTML",
                        disable_web_page_preview=False,
                    )

                except Exception as error:

                    print(
                        f"❌ Failed sending Deal "
                        f"#{deal.id} "
                        f"chunk {index + 1}:",
                        repr(error),
                    )

                    traceback.print_exc()

        except Exception as error:

            print(
                f"❌ Failed formatting Deal "
                f"#{deal.id}:",
                repr(error),
            )

            traceback.print_exc()

    # ========================================================
    # SEARCH AGAIN
    # ========================================================

    await send_search_again_prompt(
        bot,
        chat_id,
    )


# ============================================================
# GET LATEST DEALS
# ============================================================

def get_latest_deals():

    print(
        "🔎 Loading latest deals..."
    )

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

            formatted_text = format_deal(
                deal
            )

            chunks = split_telegram_message(
                formatted_text
            )

            for chunk in chunks:

                await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode="HTML",
                    disable_web_page_preview=False,
                )

        except Exception as error:

            print(
                f"❌ Latest Deal "
                f"#{deal.id} send error:",
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

    user, created = (
        get_or_create_telegram_user(
            telegram_user
        )
    )

    text = (
        message.text or ""
    ).strip()

    normalized_text = (
        text.lower().strip()
    )

    user_cache_key = (
        f"deal_filter_state_{user.user_id}"
    )

    # ========================================================
    # START
    # ========================================================

    if normalized_text.startswith(
        "/start"
    ):

        cache.delete(
            user_cache_key
        )

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
    # BACK
    # ========================================================

    if normalized_text in [
        "back",
        "⬅️ back",
        "/back",
    ]:

        cache.delete(
            user_cache_key
        )

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

    if (
        text == "🔎 Find Deals"
        or normalized_text in [
            "find deals",
            "find my deals",
            "find",
        ]
    ):

        cache.set(
            user_cache_key,
            {
                "step": "category",
            },
            timeout=1800,
        )

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

    if (
        text == "🆕 Latest Deals"
        or normalized_text in [
            "latest deals",
            "latest",
        ]
    ):

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
    # CURRENT STATE
    # ========================================================

    state = cache.get(
        user_cache_key
    )

    if not state:

        async def send():

            bot = Bot(
                token=bot_record.bot_token
            )

            try:

                await send_bot_message(
                    bot,
                    message.chat_id,
                    (
                        "Please choose an option "
                        "from the menu first."
                    ),
                    MAIN_KEYBOARD,
                )

            finally:

                await bot.shutdown()

        asyncio.run(send())

        return

    step = state.get(
        "step"
    )

    # ========================================================
    # STEP 1 - CATEGORY
    # ========================================================

    if step == "category":

        category = resolve_category(
            text
        )

        if not category:

            async def send():

                bot = Bot(
                    token=bot_record.bot_token
                )

                try:

                    await send_bot_message(
                        bot,
                        message.chat_id,
                        (
                            "❌ Category not found.\n\n"
                            "Please type a valid category.\n\n"
                            "Examples:\n"
                            "Electronics\n"
                            "Grocery\n"
                            "Fashion\n"
                            "Home\n"
                            "All Categories"
                        ),
                        MAIN_KEYBOARD,
                    )

                finally:

                    await bot.shutdown()

            asyncio.run(send())

            return

        cache.set(
            user_cache_key,
            {
                "step": "price",
                "category": category,
            },
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
    # STEP 2 - PRICE
    # ========================================================

    if step == "price":

        price_data = parse_price_input(
            text
        )

        if not price_data:

            async def send():

                bot = Bot(
                    token=bot_record.bot_token
                )

                try:

                    await send_bot_message(
                        bot,
                        message.chat_id,
                        (
                            "❌ Invalid price format.\n\n"
                            "Please enter one of these:\n\n"
                            "• 500-700\n"
                            "• 700-1000\n"
                            "• under 300\n"
                            "• above 1000\n"
                            "• any"
                        ),
                        MAIN_KEYBOARD,
                    )

                finally:

                    await bot.shutdown()

            asyncio.run(send())

            return

        category = state.get(
            "category"
        )

        if not category:

            cache.delete(
                user_cache_key
            )

            return

        cache.set(
            user_cache_key,
            {
                "step": "date",
                "category": category,
                "price": price_data,
            },
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
                    price_data["label"],
                )

            finally:

                await bot.shutdown()

        asyncio.run(send())

        return

    # ========================================================
    # STEP 3 - DATE
    # ========================================================

    if step == "date":

        date_data = parse_date_input(
            text
        )

        if not date_data:

            async def send():

                bot = Bot(
                    token=bot_record.bot_token
                )

                try:

                    await send_bot_message(
                        bot,
                        message.chat_id,
                        (
                            "❌ Invalid date format.\n\n"
                            "Please enter:\n\n"
                            "• today\n"
                            "• 7  → last 7 days\n"
                            "• 30 → last 30 days\n"
                            "• 25-08-2026 → particular date\n"
                            "• any"
                        ),
                        MAIN_KEYBOARD,
                    )

                finally:

                    await bot.shutdown()

            asyncio.run(send())

            return

        category = state.get(
            "category"
        )

        price_data = state.get(
            "price"
        )

        if not category or not price_data:

            cache.delete(
                user_cache_key
            )

            return

        async def send():

            bot = Bot(
                token=bot_record.bot_token
            )

            try:

                await send_filtered_deals(
                    bot,
                    message.chat_id,
                    category,
                    price_data,
                    date_data,
                    user_cache_key,
                )

            finally:

                await bot.shutdown()

        asyncio.run(send())

        return
