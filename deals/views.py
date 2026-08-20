from django.shortcuts import (
    render,
    redirect,
    get_object_or_404
)

from django.http import JsonResponse
from django.core.paginator import Paginator
from django.db.models import Q
from django.contrib import messages

from .models import Deal, Category
from publisher.models import PublishedChannel


# ============================================================
# DASHBOARD
# ============================================================

def dashboard(request):

    total_deals = Deal.objects.count()

    recent_deals = Deal.objects.all().order_by(
        "-created_at"
    )[:6]

    published_deals = Deal.objects.filter(
        status="published"
    ).count()

    new_deals = Deal.objects.filter(
        status="new"
    ).count()

    total_categories = Category.objects.count()

    active_categories = Category.objects.filter(
        status="active"
    ).count()

    return render(
        request,
        "deals/dashboard.html",
        {
            "total_deals": total_deals,
            "recent_deals": recent_deals,
            "published_deals": published_deals,
            "new_deals": new_deals,
            "total_categories": total_categories,
            "active_categories": active_categories,
        }
    )


# ============================================================
# DEAL LIST
# ============================================================

def deal_list(request):

    deals = Deal.objects.all().order_by(
        "-date"
    )

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    search = request.GET.get(
        "search",
        ""
    ).strip()

    if search:

        deals = deals.filter(
            Q(content__icontains=search)
            | Q(channel__icontains=search)
            | Q(product_link__icontains=search)
        )

    # --------------------------------------------------------
    # STATUS FILTER
    # --------------------------------------------------------

    selected_status = request.GET.get(
        "status",
        ""
    ).strip()

    if selected_status:

        deals = deals.filter(
            status=selected_status
        )

    # --------------------------------------------------------
    # CHANNEL FILTER
    # --------------------------------------------------------

    selected_channel = request.GET.get(
        "channel",
        ""
    ).strip()

    if selected_channel:

        deals = deals.filter(
            channel=selected_channel
        )

    # --------------------------------------------------------
    # DATE FILTER
    # --------------------------------------------------------

    date_from = request.GET.get(
        "date_from",
        ""
    ).strip()

    date_to = request.GET.get(
        "date_to",
        ""
    ).strip()

    if date_from:

        deals = deals.filter(
            date__date__gte=date_from
        )

    if date_to:

        deals = deals.filter(
            date__date__lte=date_to
        )

    # --------------------------------------------------------
    # PRICE FILTER
    # --------------------------------------------------------

    min_price = request.GET.get(
        "min_price",
        ""
    ).strip()

    max_price = request.GET.get(
        "max_price",
        ""
    ).strip()

    if min_price:

        try:
            deals = deals.filter(
                price__gte=float(min_price)
            )
        except (ValueError, TypeError):
            pass

    if max_price:

        try:
            deals = deals.filter(
                price__lte=float(max_price)
            )
        except (ValueError, TypeError):
            pass

    # --------------------------------------------------------
    # RATING FILTER
    # --------------------------------------------------------

    min_rating = request.GET.get(
        "min_rating",
        ""
    ).strip()

    if min_rating:

        try:
            deals = deals.filter(
                rating__gte=float(min_rating)
            )
        except (ValueError, TypeError):
            pass

    # --------------------------------------------------------
    # SORTING
    # --------------------------------------------------------

    sort_by = request.GET.get(
        "sort",
        "newest"
    ).strip()

    if sort_by == "oldest":

        deals = deals.order_by(
            "date"
        )

    elif sort_by == "price_low":

        deals = deals.order_by(
            "price",
            "-date"
        )

    elif sort_by == "price_high":

        deals = deals.order_by(
            "-price",
            "-date"
        )

    elif sort_by == "rating_high":

        deals = deals.order_by(
            "-rating",
            "-date"
        )

    else:

        deals = deals.order_by(
            "-date"
        )

    # --------------------------------------------------------
    # DEALS PER PAGE
    # --------------------------------------------------------

    allowed_per_page = [
        10,
        20,
        30,
        50,
        100
    ]

    try:

        per_page = int(
            request.GET.get(
                "per_page",
                10
            )
        )

    except (ValueError, TypeError):

        per_page = 10

    if per_page not in allowed_per_page:

        per_page = 10

    # --------------------------------------------------------
    # PAGINATION
    # --------------------------------------------------------

    paginator = Paginator(
        deals,
        per_page
    )

    page_number = request.GET.get(
        "page"
    )

    page_obj = paginator.get_page(
        page_number
    )

    # --------------------------------------------------------
    # CHANNELS
    # --------------------------------------------------------

    channels = PublishedChannel.objects.filter(
        status="active"
    ).order_by(
        "name"
    )

    # --------------------------------------------------------
    # ALL CHANNEL NAMES
    # Fallback in case PublishedChannel does not have
    # the same deal channel names.
    # --------------------------------------------------------

    deal_channels = Deal.objects.values_list(
        "channel",
        flat=True
    ).distinct().order_by(
        "channel"
    )

    return render(
        request,
        "deals/deals.html",
        {
            "deals": page_obj,
            "page_obj": page_obj,

            # Search
            "search": search,

            # Filters
            "selected_status": selected_status,
            "selected_channel": selected_channel,
            "date_from": date_from,
            "date_to": date_to,
            "min_price": min_price,
            "max_price": max_price,
            "min_rating": min_rating,

            # Sorting
            "sort_by": sort_by,

            # Pagination
            "per_page": per_page,
            "allowed_per_page": allowed_per_page,
            "total_deals": paginator.count,

            # Channels
            "channels": channels,
            "deal_channels": deal_channels,

            # Status choices
            "status_choices": Deal.STATUS_CHOICES,
        }
    )


# ============================================================
# CATEGORY LIST
# ============================================================

def category_list(request):

    categories = Category.objects.all().order_by(
        "name"
    )

    return render(
        request,
        "deals/categories.html",
        {
            "categories": categories
        }
    )


# ============================================================
# ADD CATEGORY
# ============================================================

def category_add(request):

    if request.method == "POST":

        name = request.POST.get(
            "name",
            ""
        ).strip()

        description = request.POST.get(
            "description",
            ""
        ).strip()

        keywords = request.POST.get(
            "keywords",
            ""
        ).strip()

        status_value = request.POST.get(
            "status",
            "active"
        ).strip()

        allowed_statuses = {
            "active",
            "inactive",
        }

        if status_value not in allowed_statuses:

            status_value = "active"

        if not name:

            messages.error(
                request,
                "Category name is required."
            )

            return redirect(
                "category-list"
            )

        if Category.objects.filter(
            name__iexact=name
        ).exists():

            messages.error(
                request,
                "This category already exists."
            )

            return redirect(
                "category-list"
            )

        Category.objects.create(
            name=name,
            description=description,
            keywords=keywords,
            status=status_value
        )

        messages.success(
            request,
            "Category added successfully."
        )

    return redirect(
        "category-list"
    )


# ============================================================
# EDIT CATEGORY
# ============================================================

def category_edit(request, category_id):

    category = get_object_or_404(
        Category,
        id=category_id
    )

    if request.method == "POST":

        name = request.POST.get(
            "name",
            ""
        ).strip()

        description = request.POST.get(
            "description",
            ""
        ).strip()

        keywords = request.POST.get(
            "keywords",
            ""
        ).strip()

        status_value = request.POST.get(
            "status",
            "active"
        ).strip()

        allowed_statuses = {
            "active",
            "inactive",
        }

        if status_value not in allowed_statuses:

            status_value = "active"

        if not name:

            messages.error(
                request,
                "Category name is required."
            )

            return redirect(
                "category-edit",
                category_id=category.id
            )

        duplicate = Category.objects.filter(
            name__iexact=name
        ).exclude(
            id=category.id
        ).exists()

        if duplicate:

            messages.error(
                request,
                "Another category with this name already exists."
            )

            return redirect(
                "category-edit",
                category_id=category.id
            )

        category.name = name
        category.description = description
        category.keywords = keywords
        category.status = status_value

        category.save()

        messages.success(
            request,
            "Category updated successfully."
        )

        return redirect(
            "category-list"
        )

    return render(
        request,
        "deals/category_edit.html",
        {
            "category": category
        }
    )


# ============================================================
# DELETE CATEGORY
# ============================================================

def category_delete(request, category_id):

    category = get_object_or_404(
        Category,
        id=category_id
    )

    if request.method == "POST":

        category.delete()

        messages.success(
            request,
            "Category deleted successfully."
        )

    return redirect(
        "category-list"
    )


# ============================================================
# TOGGLE CATEGORY
# ============================================================

def category_toggle(request, category_id):

    category = get_object_or_404(
        Category,
        id=category_id
    )

    if request.method == "POST":

        if category.status == "active":

            category.status = "inactive"

        else:

            category.status = "active"

        category.save()

        messages.success(
            request,
            "Category status updated successfully."
        )

    return redirect(
        "category-list"
    )


# ============================================================
# CATEGORY DEALS
# ============================================================

def category_deals(request, category_id):

    category = get_object_or_404(
        Category,
        id=category_id
    )

    deals = Deal.objects.all().order_by(
        "-date"
    )

    keywords = category.get_keywords_list()

    keyword_query = Q()

    for keyword in keywords:

        keyword = keyword.strip().lower()

        if not keyword:
            continue

        keyword_query |= (
            Q(content__icontains=keyword)
            | Q(product_link__icontains=keyword)
            | Q(channel__icontains=keyword)
        )

    if keywords:

        deals = deals.filter(
            keyword_query
        ).distinct()

    else:

        deals = Deal.objects.none()

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    search = request.GET.get(
        "search",
        ""
    ).strip()

    if search:

        deals = deals.filter(
            Q(content__icontains=search)
            | Q(channel__icontains=search)
            | Q(product_link__icontains=search)
        )

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    selected_status = request.GET.get(
        "status",
        ""
    ).strip()

    if selected_status:

        deals = deals.filter(
            status=selected_status
        )

    # --------------------------------------------------------
    # CHANNEL
    # --------------------------------------------------------

    selected_channel = request.GET.get(
        "channel",
        ""
    ).strip()

    if selected_channel:

        deals = deals.filter(
            channel=selected_channel
        )

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    date_from = request.GET.get(
        "date_from",
        ""
    ).strip()

    date_to = request.GET.get(
        "date_to",
        ""
    ).strip()

    if date_from:

        deals = deals.filter(
            date__date__gte=date_from
        )

    if date_to:

        deals = deals.filter(
            date__date__lte=date_to
        )

    # --------------------------------------------------------
    # PRICE
    # --------------------------------------------------------

    min_price = request.GET.get(
        "min_price",
        ""
    ).strip()

    max_price = request.GET.get(
        "max_price",
        ""
    ).strip()

    if min_price:

        try:

            deals = deals.filter(
                price__gte=float(min_price)
            )

        except (ValueError, TypeError):

            pass

    if max_price:

        try:

            deals = deals.filter(
                price__lte=float(max_price)
            )

        except (ValueError, TypeError):

            pass

    # --------------------------------------------------------
    # RATING
    # --------------------------------------------------------

    min_rating = request.GET.get(
        "min_rating",
        ""
    ).strip()

    if min_rating:

        try:

            deals = deals.filter(
                rating__gte=float(min_rating)
            )

        except (ValueError, TypeError):

            pass

    # --------------------------------------------------------
    # SORTING
    # --------------------------------------------------------

    sort_by = request.GET.get(
        "sort",
        "newest"
    ).strip()

    if sort_by == "oldest":

        deals = deals.order_by(
            "date"
        )

    elif sort_by == "price_low":

        deals = deals.order_by(
            "price",
            "-date"
        )

    elif sort_by == "price_high":

        deals = deals.order_by(
            "-price",
            "-date"
        )

    elif sort_by == "rating_high":

        deals = deals.order_by(
            "-rating",
            "-date"
        )

    else:

        deals = deals.order_by(
            "-date"
        )

    # --------------------------------------------------------
    # PAGINATION
    # --------------------------------------------------------

    allowed_per_page = [
        10,
        20,
        30,
        50,
        100
    ]

    try:

        per_page = int(
            request.GET.get(
                "per_page",
                10
            )
        )

    except (ValueError, TypeError):

        per_page = 10

    if per_page not in allowed_per_page:

        per_page = 10

    paginator = Paginator(
        deals,
        per_page
    )

    page_number = request.GET.get(
        "page"
    )

    page_obj = paginator.get_page(
        page_number
    )

    # --------------------------------------------------------
    # CHANNELS
    # --------------------------------------------------------

    deal_channels = Deal.objects.values_list(
        "channel",
        flat=True
    ).distinct().order_by(
        "channel"
    )

    return render(
        request,
        "deals/category_deals.html",
        {
            "category": category,

            "deals": page_obj,
            "page_obj": page_obj,

            "keywords": keywords,

            # Search
            "search": search,

            # Filters
            "selected_status": selected_status,
            "selected_channel": selected_channel,
            "date_from": date_from,
            "date_to": date_to,
            "min_price": min_price,
            "max_price": max_price,
            "min_rating": min_rating,

            # Sorting
            "sort_by": sort_by,

            # Pagination
            "per_page": per_page,
            "allowed_per_page": allowed_per_page,
            "matching_count": paginator.count,

            # Channels
            "deal_channels": deal_channels,

            # Status choices
            "status_choices": Deal.STATUS_CHOICES,
        }
    )


# ============================================================
# EDIT DEAL
# ============================================================

def deal_edit(request, deal_id):

    deal = get_object_or_404(
        Deal,
        id=deal_id
    )

    if request.method == "POST":

        content = request.POST.get(
            "content",
            ""
        ).strip()

        product_link = request.POST.get(
            "product_link",
            ""
        ).strip()

        status_value = request.POST.get(
            "status",
            "new"
        ).strip()

        price_value = request.POST.get(
            "price",
            ""
        ).strip()

        rating_value = request.POST.get(
            "rating",
            ""
        ).strip()

        allowed_statuses = {
            "new",
            "processed",
            "published",
            "expired",
            "rejected",
        }

        if status_value not in allowed_statuses:

            status_value = "new"

        # ----------------------------------------------------
        # PRICE
        # ----------------------------------------------------

        if price_value:

            try:

                deal.price = float(
                    price_value
                )

            except (ValueError, TypeError):

                deal.price = None

        else:

            deal.price = None

        # ----------------------------------------------------
        # RATING
        # ----------------------------------------------------

        if rating_value:

            try:

                rating_number = float(
                    rating_value
                )

                if 0 <= rating_number <= 5:

                    deal.rating = rating_number

                else:

                    deal.rating = None

            except (ValueError, TypeError):

                deal.rating = None

        else:

            deal.rating = None

        deal.content = content
        deal.product_link = product_link
        deal.status = status_value

        deal.save()

        messages.success(
            request,
            "Deal updated successfully."
        )

        return redirect(
            "deal-list"
        )

    return render(
        request,
        "deals/deal_edit.html",
        {
            "deal": deal
        }
    )


# ============================================================
# DELETE DEAL
# ============================================================

def deal_delete(request, deal_id):

    deal = get_object_or_404(
        Deal,
        id=deal_id
    )

    if request.method == "POST":

        deal.delete()

        messages.success(
            request,
            "Deal deleted successfully."
        )

    return redirect(
        "deal-list"
    )


# ============================================================
# UPDATE DEAL STATUS
# ============================================================

def deal_status_update(request, deal_id):

    if request.method != "POST":

        return JsonResponse(
            {
                "success": False,
                "error": "POST method required"
            },
            status=405
        )

    deal = get_object_or_404(
        Deal,
        id=deal_id
    )

    status_value = request.POST.get(
        "status",
        ""
    ).strip()

    allowed_statuses = {
        "new",
        "processed",
        "published",
        "expired",
        "rejected",
    }

    if status_value not in allowed_statuses:

        return JsonResponse(
            {
                "success": False,
                "error": "Invalid status"
            },
            status=400
        )

    deal.status = status_value

    deal.save()

    return JsonResponse(
        {
            "success": True,
            "status": deal.status
        }
    )


# ============================================================
# DEAL API
# ============================================================

def deal_api(request):

    if request.method != "GET":

        return JsonResponse(
            {
                "success": False,
                "error": "GET method required"
            },
            status=405
        )

    deals = Deal.objects.all().order_by(
        "-date"
    )

    # --------------------------------------------------------
    # SEARCH
    # --------------------------------------------------------

    search = request.GET.get(
        "search",
        ""
    ).strip()

    if search:

        deals = deals.filter(
            Q(content__icontains=search)
            | Q(channel__icontains=search)
            | Q(product_link__icontains=search)
        )

    # --------------------------------------------------------
    # STATUS
    # --------------------------------------------------------

    status_value = request.GET.get(
        "status",
        ""
    ).strip()

    if status_value:

        deals = deals.filter(
            status=status_value
        )

    # --------------------------------------------------------
    # CHANNEL
    # --------------------------------------------------------

    channel = request.GET.get(
        "channel",
        ""
    ).strip()

    if channel:

        deals = deals.filter(
            channel=channel
        )

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    date_from = request.GET.get(
        "date_from",
        ""
    ).strip()

    date_to = request.GET.get(
        "date_to",
        ""
    ).strip()

    if date_from:

        deals = deals.filter(
            date__date__gte=date_from
        )

    if date_to:

        deals = deals.filter(
            date__date__lte=date_to
        )

    # --------------------------------------------------------
    # PRICE
    # --------------------------------------------------------

    min_price = request.GET.get(
        "min_price",
        ""
    ).strip()

    max_price = request.GET.get(
        "max_price",
        ""
    ).strip()

    if min_price:

        try:

            deals = deals.filter(
                price__gte=float(min_price)
            )

        except (ValueError, TypeError):

            pass

    if max_price:

        try:

            deals = deals.filter(
                price__lte=float(max_price)
            )

        except (ValueError, TypeError):

            pass

    # --------------------------------------------------------
    # RATING
    # --------------------------------------------------------

    min_rating = request.GET.get(
        "min_rating",
        ""
    ).strip()

    if min_rating:

        try:

            deals = deals.filter(
                rating__gte=float(min_rating)
            )

        except (ValueError, TypeError):

            pass

    # --------------------------------------------------------
    # RESULTS
    # --------------------------------------------------------

    results = []

    for deal in deals:

        results.append(
            {
                "id": deal.id,
                "message_id": deal.message_id,
                "date": deal.date,
                "content": deal.content,
                "product_link": deal.product_link,
                "image_path": deal.image_path,
                "channel": deal.channel,

                "price": (
                    float(deal.price)
                    if deal.price is not None
                    else None
                ),

                "rating": (
                    float(deal.rating)
                    if deal.rating is not None
                    else None
                ),

                "status": deal.status,
                "created_at": deal.created_at,
                "updated_at": deal.updated_at,
            }
        )

    return JsonResponse(
        {
            "success": True,
            "count": len(results),
            "results": results,
        }
    )
