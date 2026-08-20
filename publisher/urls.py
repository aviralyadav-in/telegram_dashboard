from django.urls import path

from .views import (
    channel_list,
    add_bot,
    delete_bot,
    add_channel,
    edit_channel,
    delete_channel,
    find_chat,
    test_channel,
    publish_page,
    publish_deal,
    published_deals,
    bulk_publish_deals,
    allow_user,
    block_user,
)


urlpatterns = [

    path(
        "",
        channel_list,
        name="channels"
    ),

    path(
        "add/",
        add_channel,
        name="add-channel"
    ),

    path(
        "<int:channel_id>/edit/",
        edit_channel,
        name="edit-channel"
    ),

    path(
        "<int:channel_id>/delete/",
        delete_channel,
        name="delete-channel"
    ),

    path(
        "<int:channel_id>/test/",
        test_channel,
        name="test-channel"
    ),

    path(
        "bot/add/",
        add_bot,
        name="add-bot"
    ),

    path(
        "bot/<int:bot_id>/delete/",
        delete_bot,
        name="delete-bot"
    ),

    path(
        "find-chat/",
        find_chat,
        name="find-chat"
    ),

    path(
        "publish/",
        publish_page,
        name="publish-page"
    ),

    path(
        "publish/deal/",
        publish_deal,
        name="publish-deal"
    ),

    path(
        "publish/bulk/",
        bulk_publish_deals,
        name="bulk-publish-deals"
    ),

    path(
        "published/",
        published_deals,
        name="published-deals"
    ),

    path(
        "user/<int:permission_id>/allow/",
        allow_user,
        name="allow-user"
    ),

    path(
        "user/<int:permission_id>/block/",
        block_user,
        name="block-user"
    ),
]