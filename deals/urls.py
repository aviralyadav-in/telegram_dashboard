from django.urls import path

from .views import (
    dashboard,
    deal_list,
    deal_api,
    deal_edit,
    deal_delete,
    deal_status_update,

    category_list,
    category_add,
    category_edit,
    category_delete,
    category_toggle,
    category_deals,
)


urlpatterns = [

    # ============================================================
    # DASHBOARD
    # ============================================================

    path(
        "",
        dashboard,
        name="dashboard"
    ),


    # ============================================================
    # DEALS
    # ============================================================

    path(
        "list/",
        deal_list,
        name="deal-list"
    ),

    path(
        "api/",
        deal_api,
        name="deal-api"
    ),

    path(
        "edit/<int:deal_id>/",
        deal_edit,
        name="deal-edit"
    ),

    path(
        "delete/<int:deal_id>/",
        deal_delete,
        name="deal-delete"
    ),

    path(
        "status/<int:deal_id>/",
        deal_status_update,
        name="deal-status-update"
    ),


    # ============================================================
    # CATEGORIES
    # ============================================================

    path(
        "categories/",
        category_list,
        name="category-list"
    ),

    path(
        "categories/add/",
        category_add,
        name="category-add"
    ),

    path(
        "categories/edit/<int:category_id>/",
        category_edit,
        name="category-edit"
    ),

    path(
        "categories/delete/<int:category_id>/",
        category_delete,
        name="category-delete"
    ),

    path(
        "categories/toggle/<int:category_id>/",
        category_toggle,
        name="category-toggle"
    ),

    path(
        "categories/<int:category_id>/deals/",
        category_deals,
        name="category-deals"
    ),

]