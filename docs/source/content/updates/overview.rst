💬 Updates
==========


.. currentmodule:: pywa.types

In WhatsApp Cloud API, updates are sent to your webhook URL. PyWa currently supports the following fields:

- ``messages`` (all user related updates)
- ``message_template_status_update`` (template got approved, rejected, etc.)

.. important::

    You must subscribe to those fields in your webhook settings. Otherwise, you will not receive any updates.
    To enable it, go to your app dashboard, click on the ``Webhooks`` tab (Or the ``Configuration`` tab > ``Webhook fields``).
    Then, subscribe to the fields you want to receive.

    .. toggle::

        .. image:: ../../../../_static/guides/webhook-fields.webp
           :width: 600
           :alt: Subscribe to webhook fields
           :align: center

.. tip::

        If you do want to handle other types of updates (fields), you can use the :py:class:`~pywa.handlers.RawUpdateHandler`
        (or the :func:`~pywa.client.WhatsApp.on_raw_update` decorator) to handle them.



The supported fields are automatically handled by PyWa and converted to the following types:

- To handle updates see `Handlers <../handlers/overview.html>`_

User related updates:

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Type
     - Description
   * - :py:class:`~pywa.types.message.Message`
     - A message sent by a user (text, media, order, location, etc.)
   * - :py:class:`~pywa.types.callback.CallbackButton`
     - A callback button pressed by a user
   * - :py:class:`~pywa.types.callback.CallbackSelection`
     - A callback selection chosen by a user
   * - :py:class:`~pywa.types.message_status.MessageStatus`
     - A message status update (e.g. delivered, seen, etc.)

Account related updates:

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Type
     - Description
   * - :py:class:`~pywa.types.template.TemplateStatus`
     - A template status update (e.g. approved, rejected, etc.)

All user-related-updates have common methods:

.. currentmodule:: pywa.types.base_update

.. list-table::
   :widths: 25 75
   :header-rows: 1

   * - Method
     - Description
   * - :meth:`~BaseUserUpdate.reply_text`
     - Reply to the update with a text message
   * - :meth:`~BaseUserUpdate.reply_image`
     - Reply to the update with an image message
   * - :meth:`~BaseUserUpdate.reply_video`
     - Reply to the update with a video message
   * - :meth:`~BaseUserUpdate.reply_audio`
     - Reply to the update with an audio message
   * - :meth:`~BaseUserUpdate.reply_document`
     - Reply to the update with a document message
   * - :meth:`~BaseUserUpdate.reply_location`
     - Reply to the update with a location message
   * - :meth:`~BaseUserUpdate.reply_contact`
     - Reply to the update with a contact message
   * - :meth:`~BaseUserUpdate.reply_sticker`
     - Reply to the update with a sticker message
   * - :meth:`~BaseUserUpdate.reply_template`
     - Reply to the update with a template message
   * - :meth:`~BaseUserUpdate.reply_catalog`
     - Reply to the update with a catalog message
   * - :meth:`~BaseUserUpdate.reply_product`
     - Reply to the update with a product message
   * - :meth:`~BaseUserUpdate.reply_products`
     - Reply to the update with a list of product messages
   * - :meth:`~BaseUserUpdate.react`
     - React to the update with a emoji
   * - :meth:`~BaseUserUpdate.unreact`
     - Unreact to the update
   * - :meth:`~BaseUserUpdate.mark_as_read`
     - Mark the update as read

.. toctree::
    message
    callback_button
    callback_selection
    message_status
    template_status
    common_methods
