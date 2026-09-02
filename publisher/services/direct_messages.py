import re
import traceback

from datetime import datetime, timedelta
from html import escape

from asgiref.sync import sync_to_async

from django.core.cache import cache
from django.utils import timezone

from telegram import (
    Bot,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
)

from deals.models import Deal, Category

from publisher.models import (
    TelegramUser,
    PublishedChannel,
    UserDestinationPermission,
)

from publisher.services.user_tracking import (
    get_or_create_telegram_user,
)


# ============================================================
# CONSTANTS
# ============================================================

CACHE_TIMEOUT = 1800

MAIN_MENU = "main"
CATEGORY_STEP = "category"
PRICE_STEP = "price"
DATE_STEP = "date"


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
# CACHE
# ============================================================

def get_user_cache_key(user_id):
    return f"deal_filter_state_{user_id}"


def set_user_state(
    user_id,
    state,
):
    cache.set(
        get_user_cache_key(user_id),
        state,
        timeout=CACHE_TIMEOUT,
    )


def get_user_state(user_id):
    return cache.get(
        get_user_cache_key(user_id)
    )


def clear_user_state(user_id):
    cache.delete(
        get_user_cache_key(user_id)
    )


# ============================================================
# DATABASE
# ============================================================

@sync_to_async(thread_sensitive=True)
def get_telegram_user_from_update(
    telegram_user,
):
    return get_or_create_telegram_user(
        telegram_user
    )


@sync_to_async(thread_sensitive=True)
def check_saved_permission(user):

    if not user:
        return False

    return (
        UserDestinationPermission.objects
        .filter(
            user=user,
            is_allowed=True,
        )
        .exists()
    )


@sync_to_async(thread_sensitive=True)
def grant_user_access_for_destination(
    user,
    channel,
):
    """
    Create permission when Telegram membership has already
    been verified by the bot.
    """

    if not user or not channel:
        return False

    UserDestinationPermission.objects.update_or_create(
        user=user,
        destination=channel,
        defaults={
            "can_message": bool(
                channel.allow_direct_messages
            ),
            "can_publish": False,
            "is_allowed": True,
        },
    )

    return True


@sync_to_async(thread_sensitive=True)
def get_active_destinations():
    return list(
        PublishedChannel.objects
        .filter(
            status="active",
        )
        .select_related("bot")
    )


# ============================================================
# ACCESS CONTROL
# ============================================================

async def is_user_allowed_to_use_bot(
    user,
    bot=None,
):
    """
    Access logic:

    1. Existing allowed permission -> allow.
    2. Otherwise check active destinations.
    3. Ask Telegram whether the user is member/admin/creator.
    4. If yes, automatically create permission.
    """

    if not user:
        return False

    # --------------------------------------------------------
    # Existing permission
    # --------------------------------------------------------

    if await check_saved_permission(user):
        return True

    # --------------------------------------------------------
    # Automatic membership verification
    # --------------------------------------------------------

    if bot is None:
        return False

    destinations = (
        await get_active_destinations()
    )

    for destination in destinations:

        if not destination.bot:
            continue

        if (
            destination.bot.bot_token
            != bot.token
        ):
            continue

        chat_id = (
            destination.chat_id
            or destination.username
        )

        if not chat_id:
            continue

        try:

            member = await bot.get_chat_member(
                chat_id=chat_id,
                user_id=user.user_id,
            )

            status = member.status

            if status in {
                "member",
                "administrator",
                "creator",
            }:

                await grant_user_access_for_destination(
                    user,
                    destination,
                )

                return True

        except Exception as error:

            print(
                "⚠️ Membership check failed | "
                f"user={user.user_id} | "
                f"destination={destination.id} | "
                f"error={error}"
            )

            continue

    return False


# ============================================================
# SEND ACCESS DENIED
# ============================================================

async def send_access_denied(
    bot,
    chat_id,
):

    await bot.send_message(
        chat_id=chat_id,
        text=(
            "🚫 Access denied.\n\n"
            "You are currently blocked or not allowed "
            "to use the deal finder."
        ),
    )


# ============================================================
# BASIC SEND
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
        f"👋 Hello {name}!\n\n"
        "Welcome to MyDeals Deal Finder. 🎁\n\n"
        "Let's find the best deals for you.\n\n"
        "👇 Choose an option:"
    )

    return await send_bot_message(
        bot,
        chat_id,
        text,
        MAIN_KEYBOARD,
    )


# ============================================================
# CATEGORY MENU
# ============================================================

@sync_to_async(thread_sensitive=True)
def get_active_categories():

    return list(
        Category.objects
        .filter(
            status="active"
        )
        .order_by("name")
    )


async def send_category_menu(
    bot,
    chat_id,
):

    try:

        categories = (
            await get_active_categories()
        )

    except Exception as error:

        print(
            "❌ CATEGORY LOAD ERROR:",
            repr(error),
        )

        categories = []

    buttons = []

    for category in categories[:20]:

        buttons.append(
            [
                InlineKeyboardButton(
                    text=category.name,
                    callback_data=(
                        f"category:{category.id}"
                    ),
                )
            ]
        )

    buttons.append(
        [
            InlineKeyboardButton(
                text="📦 All Categories",
                callback_data="category:all",
            )
        ]
    )

    keyboard = InlineKeyboardMarkup(
        buttons
    )

    await bot.send_message(
        chat_id=chat_id,
        text=(
            "🔎 <b>Find Deals</b>\n\n"
            "Choose a category below.\n\n"
            "You can also type the category name.\n\n"
            "Examples:\n"
            "• Electronics\n"
            "• Grocery\n"
            "• Fashion\n"
            "• Home\n"
            "• All Categories"
        ),
        parse_mode="HTML",
        reply_markup=keyboard,
    )


# ============================================================
# CATEGORY RESOLUTION
# ============================================================

@sync_to_async(thread_sensitive=True)
def resolve_category_db(
    user_input,
):

    value = (
        user_input or ""
    ).strip().lower()

    if not value:
        return None

    if value in {
        "all",
        "all categories",
        "all category",
        "any",
        "*",
    }:
        return "All Categories"

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

    alias_name = aliases.get(value)

    if alias_name:

        category = (
            Category.objects
            .filter(
                name__iexact=alias_name,
                status="active",
            )
            .first()
        )

        if category:
            return category.name

    categories = (
        Category.objects
        .filter(
            status="active"
        )
    )

    for category in categories:

        db_name = category.name.lower()

        if (
            value in db_name
            or db_name in value
        ):
            return category.name

    return None


@sync_to_async(thread_sensitive=True)
def get_category_by_id(
    category_id,
):

    try:

        return (
            Category.objects
            .filter(
                id=int(category_id),
                status="active",
            )
            .first()
        )

    except Exception:

        return None


# ============================================================
# PRICE
# ============================================================

def parse_price_input(
    user_input,
):

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

    if value in {
        "any",
        "any price",
        "all",
        "no filter",
    }:

        return {
            "type": "any",
            "label": "Any Price",
        }

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
# DATE
# ============================================================

def parse_date_input(
    user_input,
):

    value = (
        user_input or ""
    ).strip().lower()

    if value in {
        "any",
        "any date",
        "all",
        "no filter",
    }:

        return {
            "type": "any",
            "label": "Any Date",
        }

    if value in {
        "today",
        "todays",
        "today's",
    }:

        return {
            "type": "today",
            "label": "Today",
        }

    if re.match(
        r"^\d+$",
        value,
    ):

        days = int(value)

        if days <= 0 or days > 3650:
            return None

        return {
            "type": "days",
            "days": days,
            "label": f"Last {days} Days",
        }

    for date_format in [
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d.%m.%Y",
    ]:

        try:

            selected_date = (
                datetime.strptime(
                    value,
                    date_format,
                ).date()
            )

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
# FIND DEALS
# ============================================================

@sync_to_async(thread_sensitive=True)
def find_matching_deals_sync(
    category,
    price_data,
    date_data,
):

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

    # --------------------------------------------------------
    # PRICE
    # --------------------------------------------------------

    if price_data:

        price_type = (
            price_data.get("type")
        )

        if price_type == "under":

            deals = deals.filter(
                price__lt=price_data["max"]
            )

        elif price_type == "above":

            deals = deals.filter(
                price__gt=price_data["min"]
            )

        elif price_type == "range":

            deals = deals.filter(
                price__gte=price_data["min"],
                price__lte=price_data["max"],
            )

        elif price_type == "single":

            deals = deals.filter(
                price=price_data["min"]
            )

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    if date_data:

        date_type = (
            date_data.get("type")
        )

        now = timezone.now()

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

            deals = deals.filter(
                date__gte=start,
                date__lt=end,
            )

        elif date_type == "days":

            deals = deals.filter(
                date__gte=(
                    now
                    - timedelta(
                        days=date_data["days"]
                    )
                )
            )

        elif date_type == "specific":

            selected_date = (
                date_data["date"]
            )

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

            deals = deals.filter(
                date__gte=start,
                date__lt=end,
            )

    deals = list(
        deals[:300]
    )

    # --------------------------------------------------------
    # CATEGORY
    # --------------------------------------------------------

    if category == "All Categories":
        return deals[:20]

    category_obj = (
        Category.objects
        .filter(
            name__iexact=category,
            status="active",
        )
        .first()
    )

    keywords = []

    if category_obj:

        keywords = (
            category_obj.get_keywords_list()
            or []
        )

    results = []

    for deal in deals:

        content = (
            f"{deal.content or ''} "
            f"{deal.product_link or ''}"
        ).lower()

        if keywords:

            matched = any(
                keyword.lower() in content
                for keyword in keywords
                if keyword
            )

        else:

            matched = (
                category.lower()
                in content
            )

        if matched:

            results.append(
                deal
            )

        if len(results) >= 20:
            break

    return results


# ============================================================
# FORMAT DEAL
# ============================================================

def format_deal(
    deal,
):

    content = escape(
        deal.content
        or "Deal available"
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
            "📅 "
            f"{deal.date.strftime('%d %b %Y')}\n"
        )

    if deal.channel:

        text += (
            "📢 Source: "
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
# FIND MY DEALS BUTTON
# ============================================================

async def get_find_deals_keyboard(
    bot,
):

    me = await bot.get_me()

    if not me.username:
        raise ValueError(
            "Telegram bot username could not be determined."
        )

    url = (
        f"https://t.me/{me.username}"
        "?start=find_deals"
    )

    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="🔎 Find My Deals",
                    url=url,
                )
            ]
        ]
    )


# ============================================================
# SPLIT
# ============================================================

def split_telegram_message(
    text,
    max_length=3500,
):

    if len(text) <= max_length:
        return [text]

    chunks = []
    current = ""

    for line in text.split("\n"):

        candidate = (
            f"{current}\n{line}"
            if current
            else line
        )

        if len(candidate) <= max_length:

            current = candidate
            continue

        if current:

            chunks.append(
                current.rstrip()
            )

            current = ""

        if len(line) <= max_length:

            current = line
            continue

        for start in range(
            0,
            len(line),
            max_length,
        ):

            chunks.append(
                line[
                    start:start + max_length
                ]
            )

    if current:

        chunks.append(
            current.rstrip()
        )

    return chunks


# ============================================================
# SEND DEAL LIST
# ============================================================

async def send_deal_list(
    bot,
    chat_id,
    deals,
    header,
):

    await bot.send_message(
        chat_id=chat_id,
        text=header,
        parse_mode="HTML",
        reply_markup=MAIN_KEYBOARD,
    )

    find_keyboard = (
        await get_find_deals_keyboard(
            bot
        )
    )

    for deal in deals:

        try:

            text = format_deal(
                deal
            )

            chunks = split_telegram_message(
                text
            )

            for index, chunk in enumerate(
                chunks
            ):

                await bot.send_message(
                    chat_id=chat_id,
                    text=chunk,
                    parse_mode="HTML",
                    disable_web_page_preview=False,
                    reply_markup=(
                        find_keyboard
                        if index == 0
                        else None
                    ),
                )

        except Exception as error:

            print(
                f"❌ Deal #{deal.id} send error:",
                repr(error),
            )

            traceback.print_exc()


# ============================================================
# FILTERED DEALS
# ============================================================

async def send_filtered_deals(
    bot,
    chat_id,
    category,
    price_data,
    date_data,
    user_id,
):

    try:

        deals = (
            await find_matching_deals_sync(
                category,
                price_data,
                date_data,
            )
        )

    except Exception as error:

        print(
            "❌ FIND DEALS ERROR:",
            repr(error),
        )

        traceback.print_exc()

        await bot.send_message(
            chat_id=chat_id,
            text=(
                "⚠️ Sorry, deals fetch karte time "
                "problem aa gayi."
            ),
            reply_markup=MAIN_KEYBOARD,
        )

        return

    if not deals:

        await bot.send_message(
            chat_id=chat_id,
            text=(
                "😔 No deals found.\n\n"
                f"📂 Category: {category}\n"
                f"💰 Price: {price_data['label']}\n"
                f"📅 Date: {date_data['label']}\n\n"
                "Try another search."
            ),
            reply_markup=MAIN_KEYBOARD,
        )

        set_user_state(
            user_id,
            {
                "step": CATEGORY_STEP
            },
        )

        await send_category_menu(
            bot,
            chat_id,
        )

        return

    set_user_state(
        user_id,
        {
            "step": CATEGORY_STEP
        },
    )

    header = (
        f"🎯 <b>Found {len(deals)} deal(s)!</b>\n\n"
        f"📂 {escape(category)}\n"
        f"💰 {escape(price_data['label'])}\n"
        f"📅 {escape(date_data['label'])}"
    )

    await send_deal_list(
        bot,
        chat_id,
        deals,
        header,
    )

    await bot.send_message(
        chat_id=chat_id,
        text=(
            "🔎 Want to search again?\n"
            "Choose <b>Find Deals</b> below."
        ),
        parse_mode="HTML",
        reply_markup=MAIN_KEYBOARD,
    )


# ============================================================
# LATEST DEALS
# ============================================================

@sync_to_async(thread_sensitive=True)
def get_latest_deals_sync():

    return list(
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


async def send_latest_deals(
    bot,
    chat_id,
):

    try:

        deals = (
            await get_latest_deals_sync()
        )

    except Exception as error:

        print(
            "❌ LATEST DEALS ERROR:",
            repr(error),
        )

        await bot.send_message(
            chat_id=chat_id,
            text=(
                "⚠️ Latest deals fetch karte time "
                "problem aa gayi."
            ),
            reply_markup=MAIN_KEYBOARD,
        )

        return

    if not deals:

        await bot.send_message(
            chat_id=chat_id,
            text=(
                "😔 No deals available right now."
            ),
            reply_markup=MAIN_KEYBOARD,
        )

        return

    await send_deal_list(
        bot,
        chat_id,
        deals,
        (
            "🆕 <b>Latest Deals</b>\n\n"
            "Here are the newest deals:"
        ),
    )


# ============================================================
# CALLBACK
# ============================================================

async def handle_callback_query(
    bot,
    update,
):

    query = update.callback_query

    if not query:
        return

    telegram_user = query.from_user

    user, created = (
        await get_telegram_user_from_update(
            telegram_user
        )
    )

    allowed = (
        await is_user_allowed_to_use_bot(
            user,
            bot,
        )
    )

    try:
        await query.answer()
    except Exception:
        pass

    if not allowed:

        try:
            await query.answer(
                "🚫 Access denied.",
                show_alert=True,
            )
        except Exception:
            pass

        await send_access_denied(
            bot,
            query.message.chat_id,
        )

        return

    data = (
        query.data or ""
    )

    chat_id = (
        query.message.chat_id
    )

    user_id = user.user_id

    # --------------------------------------------------------
    # CATEGORY
    # --------------------------------------------------------

    if data.startswith(
        "category:"
    ):

        category_id = (
            data.split(
                ":",
                1,
            )[1]
        )

        if category_id == "all":

            category_name = (
                "All Categories"
            )

        else:

            category = (
                await get_category_by_id(
                    category_id
                )
            )

            if not category:

                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        "❌ Category is no longer available."
                    ),
                    reply_markup=MAIN_KEYBOARD,
                )

                return

            category_name = (
                category.name
            )

        set_user_state(
            user_id,
            {
                "step": PRICE_STEP,
                "category": category_name,
            },
        )

        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"✅ Category: <b>"
                f"{escape(category_name)}"
                f"</b>\n\n"
                "💰 Now enter your price range.\n\n"
                "Examples:\n"
                "• <code>any</code>\n"
                "• <code>500-1000</code>\n"
                "• <code>500-4000</code>\n"
                "• <code>under 500</code>\n"
                "• <code>above 2000</code>\n"
                "• <code>2000</code>"
            ),
            parse_mode="HTML",
            reply_markup=MAIN_KEYBOARD,
        )

        return


# ============================================================
# PRIVATE MESSAGE
# ============================================================

async def handle_private_message(
    bot_record,
    update,
    bot,
):

    message = update.message

    if not message:
        return

    if not message.chat:
        return

    # --------------------------------------------------------
    # ONLY PRIVATE CHAT
    # --------------------------------------------------------

    if message.chat.type != "private":

        print(
            "⏭️ Ignored non-private message | "
            f"chat_type={message.chat.type} | "
            f"chat_id={message.chat.id}"
        )

        return

    if not message.from_user:
        return

    telegram_user = (
        message.from_user
    )

    # --------------------------------------------------------
    # USER
    # --------------------------------------------------------

    try:

        user, created = (
            await get_telegram_user_from_update(
                telegram_user
            )
        )

    except Exception as error:

        print(
            "❌ TELEGRAM USER ERROR:",
            repr(error),
        )

        traceback.print_exc()

        return

    # --------------------------------------------------------
    # ACCESS
    # --------------------------------------------------------

    allowed = (
        await is_user_allowed_to_use_bot(
            user,
            bot,
        )
    )

    if not allowed:

        print(
            "🚫 BOT ACCESS DENIED | "
            f"USER ID: {user.user_id}"
        )

        await send_access_denied(
            bot,
            message.chat_id,
        )

        return

    # --------------------------------------------------------
    # TEXT
    # --------------------------------------------------------

    text = (
        message.text or ""
    ).strip()

    normalized = (
        text.lower()
    )

    user_id = user.user_id

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    if normalized.startswith(
        "/start"
    ):

        clear_user_state(
            user_id
        )

        parts = normalized.split(
            maxsplit=1
        )

        payload = (
            parts[1].strip()
            if len(parts) > 1
            else ""
        )

        if payload == "find_deals":

            set_user_state(
                user_id,
                {
                    "step": CATEGORY_STEP
                },
            )

            await send_category_menu(
                bot,
                message.chat_id,
            )

            return

        await send_main_menu(
            bot,
            message.chat_id,
            telegram_user.first_name,
        )

        return

    # --------------------------------------------------------
    # BACK
    # --------------------------------------------------------

    if normalized in {
        "back",
        "⬅️ back",
        "/back",
    }:

        clear_user_state(
            user_id
        )

        await send_main_menu(
            bot,
            message.chat_id,
            telegram_user.first_name,
        )

        return

    # --------------------------------------------------------
    # FIND DEALS
    # --------------------------------------------------------

    if (
        text == "🔎 Find Deals"
        or normalized in {
            "find deals",
            "find my deals",
            "find",
        }
    ):

        set_user_state(
            user_id,
            {
                "step": CATEGORY_STEP
            },
        )

        await send_category_menu(
            bot,
            message.chat_id,
        )

        return

    # --------------------------------------------------------
    # LATEST DEALS
    # --------------------------------------------------------

    if (
        text == "🆕 Latest Deals"
        or normalized in {
            "latest deals",
            "latest",
        }
    ):

        await send_latest_deals(
            bot,
            message.chat_id,
        )

        return

    # --------------------------------------------------------
    # STATE
    # --------------------------------------------------------

    state = get_user_state(
        user_id
    )

    if not state:

        await send_main_menu(
            bot,
            message.chat_id,
            telegram_user.first_name,
        )

        return

    step = state.get(
        "step"
    )

    # ========================================================
    # CATEGORY
    # ========================================================

    if step == CATEGORY_STEP:

        category = (
            await resolve_category_db(
                text
            )
        )

        if not category:

            await bot.send_message(
                chat_id=message.chat_id,
                text=(
                    "❌ Category not found.\n\n"
                    "Please type a valid category or "
                    "choose one from the category menu."
                ),
                reply_markup=MAIN_KEYBOARD,
            )

            await send_category_menu(
                bot,
                message.chat_id,
            )

            return

        set_user_state(
            user_id,
            {
                "step": PRICE_STEP,
                "category": category,
            },
        )

        await bot.send_message(
            chat_id=message.chat_id,
            text=(
                f"✅ Category: <b>"
                f"{escape(category)}"
                f"</b>\n\n"
                "💰 Now enter your price range.\n\n"
                "Examples:\n"
                "• <code>any</code>\n"
                "• <code>500-1000</code>\n"
                "• <code>500-4000</code>\n"
                "• <code>under 500</code>\n"
                "• <code>above 2000</code>\n"
                "• <code>2000</code>"
            ),
            parse_mode="HTML",
            reply_markup=MAIN_KEYBOARD,
        )

        return

    # ========================================================
    # PRICE
    # ========================================================

    if step == PRICE_STEP:

        price_data = parse_price_input(
            text
        )

        if not price_data:

            await bot.send_message(
                chat_id=message.chat_id,
                text=(
                    "❌ Invalid price format.\n\n"
                    "Examples:\n"
                    "• <code>any</code>\n"
                    "• <code>500-1000</code>\n"
                    "• <code>under 500</code>\n"
                    "• <code>above 2000</code>\n"
                    "• <code>2000</code>"
                ),
                parse_mode="HTML",
                reply_markup=MAIN_KEYBOARD,
            )

            return

        category = (
            state.get("category")
        )

        if not category:

            set_user_state(
                user_id,
                {
                    "step": CATEGORY_STEP
                },
            )

            await send_category_menu(
                bot,
                message.chat_id,
            )

            return

        set_user_state(
            user_id,
            {
                "step": DATE_STEP,
                "category": category,
                "price": price_data,
            },
        )

        await bot.send_message(
            chat_id=message.chat_id,
            text=(
                f"✅ Category: <b>"
                f"{escape(category)}"
                f"</b>\n"
                f"✅ Price: <b>"
                f"{escape(price_data['label'])}"
                f"</b>\n\n"
                "📅 Finally, enter the date range.\n\n"
                "Examples:\n"
                "• <code>today</code>\n"
                "• <code>7</code> → last 7 days\n"
                "• <code>30</code> → last 30 days\n"
                "• <code>25-08-2026</code> → particular date\n"
                "• <code>any</code>"
            ),
            parse_mode="HTML",
            reply_markup=MAIN_KEYBOARD,
        )

        return

    # ========================================================
    # DATE
    # ========================================================

    if step == DATE_STEP:

        date_data = parse_date_input(
            text
        )

        if not date_data:

            await bot.send_message(
                chat_id=message.chat_id,
                text=(
                    "❌ Invalid date format.\n\n"
                    "Examples:\n"
                    "• <code>today</code>\n"
                    "• <code>7</code>\n"
                    "• <code>30</code>\n"
                    "• <code>25-08-2026</code>\n"
                    "• <code>any</code>"
                ),
                parse_mode="HTML",
                reply_markup=MAIN_KEYBOARD,
            )

            return

        category = (
            state.get("category")
        )

        price_data = (
            state.get("price")
        )

        if (
            not category
            or not price_data
        ):

            set_user_state(
                user_id,
                {
                    "step": CATEGORY_STEP
                },
            )

            await send_category_menu(
                bot,
                message.chat_id,
            )

            return

        await send_filtered_deals(
            bot,
            message.chat_id,
            category,
            price_data,
            date_data,
            user_id,
        )

        return

    # ========================================================
    # UNKNOWN STATE
    # ========================================================

    clear_user_state(
        user_id
    )

    await send_main_menu(
        bot,
        message.chat_id,
        telegram_user.first_name,
    )
