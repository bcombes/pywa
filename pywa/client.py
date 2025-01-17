"""The WhatsApp client."""

from __future__ import annotations

__all__ = ["WhatsApp"]

import hashlib
import mimetypes
import os
import requests
from typing import Iterable, BinaryIO
from pywa.api import WhatsAppCloudApi
from pywa.utils import Flask, FastAPI
from pywa.webhook import Webhook
from pywa.handlers import Handler, HandlerDecorators  # noqa
from pywa.types import (
    Button, SectionList, Message, Contact, MediaUrlResponse,
    ProductsSection, BusinessProfile, Industry, CommerceSettings, NewTemplate, Template, TemplateResponse, ButtonUrl
)


def resolve_keyboard_param(keyboard: Iterable[Button] | ButtonUrl | SectionList) -> tuple[str, dict]:
    """
    Resolve keyboard parameters to a type and an action dict.
    """
    if isinstance(keyboard, SectionList):
        return "list", keyboard.to_dict()
    elif isinstance(keyboard, ButtonUrl):
        return "cta_url", keyboard.to_dict()
    else:
        return "button", {"buttons": tuple(b.to_dict() for b in keyboard)}


def resolve_media_param(
        wa: WhatsApp,
        media: str | bytes | BinaryIO,
        mime_type: str | None,
        filename: str | None,
) -> tuple[bool, str]:
    """
    Internal method to resolve media parameters. Returns a tuple of (is_url, media_id_or_url).
    """
    if isinstance(media, str):
        if media.startswith(("https://", "http://")):
            return True, media
        elif not os.path.isfile(media) and media.isdigit():
            return False, media  # assume it's a media ID
        else:  # assume it's a file path
            if not (mt := mimetypes.guess_type(media)[0] or mime_type):
                raise ValueError(f"Could not determine the mime type of the file {media!r}. Please provide a mime type.")
            return False, wa.upload_media(
                media=media,
                mime_type=mt,
                filename=filename or os.path.basename(media)
            )
    else:
        if not mime_type or not filename:
            msg = "When sending media as bytes or a file object a {} must be provided."
            raise ValueError(msg.format("mime_type and filename" if not mime_type and not filename else
                                        ("mime_type" if not mime_type else "filename")))
        return False, wa.api.upload_media(media=media, mime_type=mime_type, filename=filename)['id']


_MISSING = object()


class WhatsApp(HandlerDecorators):
    def __init__(
            self,
            phone_id: str | int,
            token: str,
            base_url: str = "https://graph.facebook.com",
            api_version: float | int = 18.0,
            session: requests.Session | None = None,
            server: Flask | FastAPI | None = None,
            webhook_endpoint: str = "/",
            verify_token: str | None = None,
            filter_updates: bool = True,
            business_account_id: str | int | None = None,
    ) -> None:
        """
        Initialize the WhatsApp client.
            - Full documentation on `pywa.readthedocs.io <https://pywa.readthedocs.io>`_.

        Example without webhook:

            >>> from pywa import WhatsApp
            >>> wa = WhatsApp(phone_id="100944",token="EAADKQl9oJxx")

        Example with webhook (using Flask):

            >>> from pywa import WhatsApp
            >>> from flask import Flask
            >>> flask_app = Flask(__name__)
            >>> wa = WhatsApp(
            ...     phone_id="100944",
            ...     token="EAADKQl9oJxx",
            ...     server=flask_app,
            ...     verify_token="my_verify_token",
            ... )
            >>> @wa.on_message()
            ... def message_handler(_: WhatsApp, msg: Message): print(msg)
            >>> flask_app.run()  # or by using a WSGI server (e.g. gunicorn, waitress, etc.)

        Args:
            phone_id: The Phone number ID (Not the phone number itself, the ID can be found in the App settings).
            token: The token of the WhatsApp account (In production, you should
             `use permanent token <https://developers.facebook.com/docs/whatsapp/business-management-api/get-started>`_).
            base_url: The base URL of the WhatsApp API (default: ``https://graph.facebook.com``).
            api_version: The API version of the WhatsApp API (default: ``18.0``).
            session: The session to use for requests (default: new ``requests.Session()``, Do not use the same
             session across multiple WhatsApp clients!)
            server: The Flask or FastAPI app instance to use for the webhook.
            webhook_endpoint: The endpoint to listen for incoming messages (default: ``/``).
            verify_token: The verify token of the registered webhook (Required when ``server`` is provided).
            filter_updates: Whether to filter out updates that not sent to this phone number (default: ``True``, does
                not apply to raw updates).
            business_account_id: The business account ID of the WhatsApp account (optional, required for some API
                methods).
        """
        self.phone_id = str(phone_id)
        self.business_account_id = str(business_account_id) if business_account_id is not None else None
        self.api = WhatsAppCloudApi(
            phone_id=self.phone_id,
            token=token,
            session=session or requests.Session(),
            base_url=base_url,
            api_version=float(api_version),
        )
        if server is not None:
            if verify_token is None:
                raise ValueError("When listening for incoming messages, a verify token must be provided.")
            self.webhook = Webhook(
                wa_client=self,
                server=server,
                verify_token=verify_token,
                webhook_endpoint=webhook_endpoint,
                filter_updates=filter_updates,
            )
        else:
            self.webhook = None

    def __str__(self) -> str:
        return f"WhatApp(phone_id={self.phone_id!r})"

    def __repr__(self) -> str:
        return self.__str__()

    def add_handlers(self, *handlers: Handler):
        """
        Add handlers programmatically instead of using decorators.

        Example:

            >>> from pywa.handlers import MessageHandler, CallbackButtonHandler
            >>> from pywa import filters as fil
            >>> print_message = lambda _, msg: print(msg)
            >>> wa = WhatsApp(...)
            >>> wa.add_handlers(
            ...     MessageHandler(print_message, fil.text),
            ...     CallbackButtonHandler(print_message),
            ... )
        """
        if self.webhook is None:
            raise ValueError("You must initialize the WhatsApp client with an web server"
                             " (Flask or FastAPI) in order to handle incoming messages.")
        for handler in handlers:
            self.webhook.handlers[handler.__class__].append(handler)

    def send_message(
            self,
            to: str | int,
            text: str,
            header: str | None = None,
            footer: str | None = None,
            keyboard: Iterable[Button] | ButtonUrl | SectionList | None = None,
            preview_url: bool = False,
            reply_to_message_id: str | None = None,
    ) -> str:
        """
        Send a message to a WhatsApp user.

        Example:

            >>> wa = WhatsApp(...)
            >>> wa.send_message(
            ...     to="1234567890",
            ...     text="Hello from PyWa! (https://github.com/david-lev/pywa)",
            ...     preview_url=True,
            ... )

        Example with keyboard buttons:

            >>> from pywa.types import Button
            >>> wa = WhatsApp(...)
            >>> wa.send_message(
            ...     to="1234567890",
            ...     header="Hello from PyWa!",
            ...     text="What can I help you with?",
            ...     footer="Powered by PyWa",
            ...     keyboard=[
            ...         Button("Help", data="help"),
            ...         Button("About", data="about"),
            ...     ],
            ... )

        Example with a section list:
            >>> from pywa.types import SectionList, Section, SectionRow
            >>> wa = WhatsApp(...)
            >>> wa.send_message(
            ...     to="1234567890",
            ...     header="Hello from PyWa!",
            ...     text="What can I help you with?",
            ...     footer="Powered by PyWa",
            ...     keyboard=SectionList(
            ...         button_title="Choose an option",
            ...         sections=[
            ...             Section(
            ...                 title="Help",
            ...                 rows=[
            ...                     SectionRow(
            ...                         title="Help",
            ...                         callback_data="help",
            ...                         description="Get help with PyWa",
            ...                     ),
            ...                     SectionRow(
            ...                         title="About",
            ...                         callback_data="about",
            ...                         description="Learn more about PyWa",
            ...                     ),
            ...                 ],
            ...             ),
            ...            Section(
            ...                 title="Other",
            ...                 rows=[
            ...                     SectionRow(
            ...                         title="GitHub",
            ...                         callback_data="github",
            ...                         description="View the PyWa GitHub repository",
            ...                     ),
            ...                 ],
            ...             ),
            ...         ],
            ...     ),
            ... )


        Args:
            to: The phone ID of the WhatsApp user.
            text: The text to send (`markdown <https://faq.whatsapp.com/539178204879377>`_ allowed, max 4096 characters).
            header: The header of the message (if keyboard is provided, optional, up to 60 characters,
             no `markdown <https://faq.whatsapp.com/539178204879377>`_ allowed).
            footer: The footer of the message (if keyboard is provided, optional, up to 60 characters,
             `markdown <https://faq.whatsapp.com/539178204879377>`_ has no effect).
            keyboard: The keyboard to send with the message (optional).
            preview_url: Whether to show a preview of the URL in the message (if any).
            reply_to_message_id: The message ID to reply to (optional).

        Returns:
            The message ID of the sent message.
        """
        if not keyboard:
            return self.api.send_text_message(
                to=str(to),
                text=text,
                preview_url=preview_url,
                reply_to_message_id=reply_to_message_id,
            )['messages'][0]['id']
        type_, kb = resolve_keyboard_param(keyboard)
        return self.api.send_interactive_message(
            to=str(to),
            type_=type_,
            action=kb,
            header={
                "type": "text",
                "text": header,
            } if header else None,
            body=text,
            footer=footer,
        )['messages'][0]['id']

    send_text = send_message  # alias

    def send_image(
            self,
            to: str | int,
            image: str | bytes | BinaryIO,
            caption: str | None = None,
            body: str | None = None,
            footer: str | None = None,
            buttons: Iterable[Button] | ButtonUrl | None = None,
            reply_to_message_id: str | None = None,
            mime_type: str | None = None,
    ) -> str:
        """
        Send an image to a WhatsApp user.
            - Images must be 8-bit, RGB or RGBA.

        Example:

            >>> wa = WhatsApp(...)
            >>> wa.send_image(
            ...     to="1234567890",
            ...     image="https://example.com/image.png",
            ...     caption="This is an image!",
            ... )

        Args:
            to: The phone ID of the WhatsApp user.
            image: The image to send (either a media ID, URL, file path, bytes, or an open file object. When buttons are
             provided, only URL is supported).
            caption: The caption of the image (optional, `markdown <https://faq.whatsapp.com/539178204879377>`_ allowed).
            body: The body of the message (optional, up to 1024 characters,
             `markdown <https://faq.whatsapp.com/539178204879377>`_ allowed, if buttons are provided and body is not
             provided, caption will be used as the body)
            footer: The footer of the message (if buttons is provided, optional,
             `markdown <https://faq.whatsapp.com/539178204879377>`_ has no effect).
            buttons: The buttons to send with the image (optional).
            reply_to_message_id: The message ID to reply to (optional, only works if buttons provided).
            mime_type: The mime type of the image (optional, required when sending an image as bytes or a file object, 
             or file path that does not have an extension).

        Returns:
            The message ID of the sent image message.
        """
        is_url, image = resolve_media_param(wa=self, media=image, mime_type=mime_type, filename="image.jpg")
        if not buttons:
            return self.api.send_media(
                to=str(to),
                media_id_or_url=image,
                is_url=is_url,
                media_type="image",
                caption=caption,
            )['messages'][0]['id']
        if not body and not caption:
            raise ValueError("Either body or caption must be provided when sending an image with buttons.")
        type_, kb = resolve_keyboard_param(buttons)
        return self.api.send_interactive_message(
            to=str(to),
            type_=type_,
            action=kb,
            header={
                "type": "image",
                "image": {
                    "link" if is_url else "id": image,
                }
            },
            body=body or caption,
            footer=footer,
            reply_to_message_id=reply_to_message_id,
        )['messages'][0]['id']

    def send_video(
            self,
            to: str | int,
            video: str | bytes | BinaryIO,
            caption: str | None = None,
            body: str | None = None,
            footer: str | None = None,
            buttons: Iterable[Button] | ButtonUrl | None = None,
            reply_to_message_id: str | None = None,
            mime_type: str | None = None,
    ) -> str:
        """
        Send a video to a WhatsApp user.
            - Only H.264 video codec and AAC audio codec is supported.
            - Videos with a single audio stream or no audio stream are supported.

        Example:

            >>> wa = WhatsApp(...)
            >>> wa.send_video(
            ...     to="1234567890",
            ...     video="https://example.com/video.mp4",
            ...     caption="This is a video",
            ... )

        Args:
            to: The phone ID of the WhatsApp user.
            video: The video to send (either a media ID, URL, file path, bytes, or an open file object. When buttons are
             provided, only URL is supported).
            caption: The caption of the video (optional, `markdown <https://faq.whatsapp.com/539178204879377>`_ allowed).
            body: The body of the message (optional, up to 1024 characters,
             `markdown <https://faq.whatsapp.com/539178204879377>`_ allowed, if buttons are provided and body is not
             provided, caption will be used as the body)
            footer: The footer of the message (if buttons is provided, optional,
             `markdown <https://faq.whatsapp.com/539178204879377>`_ has no effect).
            buttons: The buttons to send with the video (optional).
            reply_to_message_id: The message ID to reply to (optional, only works if buttons provided).
            mime_type: The mime type of the video (optional, required when sending a video as bytes or a file object,
             or file path that does not have an extension).

        Returns:
            The message ID of the sent video.
        """
        is_url, video = resolve_media_param(wa=self, media=video, mime_type=mime_type, filename="video.mp4")
        if not buttons:
            return self.api.send_media(
                to=str(to),
                media_id_or_url=video,
                is_url=is_url,
                media_type="video",
                caption=caption,
            )['messages'][0]['id']
        if not body and not caption:
            raise ValueError("Either body or caption must be provided when sending a video with buttons.")
        type_, kb = resolve_keyboard_param(buttons)
        return self.api.send_interactive_message(
            to=str(to),
            type_=type_,
            action=kb,
            header={
                "type": "video",
                "video": {
                    "link" if is_url else "id": video,
                }
            },
            body=body or caption,
            footer=footer,
            reply_to_message_id=reply_to_message_id,
        )['messages'][0]['id']

    def send_document(
            self,
            to: str | int,
            document: str | bytes | BinaryIO,
            filename: str | None = None,
            caption: str | None = None,
            body: str | None = None,
            footer: str | None = None,
            buttons: Iterable[Button] | ButtonUrl | None = None,
            reply_to_message_id: str | None = None,
            mime_type: str | None = None,
    ) -> str:
        """
        Send a document to a WhatsApp user.

        Example:

            >>> wa = WhatsApp(...)
            >>> wa.send_document(
            ...     to="1234567890",
            ...     document="https://example.com/example_123.pdf",
            ...     filename="example.pdf",
            ...     caption="Example PDF"
            ... )


        Args:
            to: The phone ID of the WhatsApp user.
            document: The document to send (either a media ID, URL, file path, bytes, or an open file object. When
             buttons are provided, only URL is supported).
            filename: The filename of the document (optional, The extension of the filename will specify what format the
             document is displayed as in WhatsApp).
            caption: The caption of the document (optional).
            body: The body of the message (optional, up to 1024 characters,
             `markdown <https://faq.whatsapp.com/539178204879377>`_ allowed, if buttons are provided and body is not
             provided, caption will be used as the body)
            footer: The footer of the message (if buttons is provided, optional,
             `markdown <https://faq.whatsapp.com/539178204879377>`_ has no effect).
            buttons: The buttons to send with the document (optional).
            reply_to_message_id: The message ID to reply to (optional, only works if buttons provided).
            mime_type: The mime type of the document (optional, required when sending a document as bytes or a file
             object, or file path that does not have an extension).

        Returns:
            The message ID of the sent document.
        """
        is_url, document = resolve_media_param(
            wa=self,
            media=document,
            mime_type=mime_type,
            filename=filename
        )
        if not buttons:
            return self.api.send_media(
                to=str(to),
                media_id_or_url=document,
                is_url=is_url,
                media_type="document",
                caption=caption,
                filename=filename,
            )['messages'][0]['id']
        if not body and not caption:
            raise ValueError("Either body or caption must be provided when sending a document with buttons.")
        type_, kb = resolve_keyboard_param(buttons)
        return self.api.send_interactive_message(
            to=str(to),
            type_=type_,
            action=kb,
            header={
                "type": "document",
                "document": {
                    "link" if is_url else "id": document,
                    "filename": filename,
                }
            },
            body=body or caption,
            footer=footer,
            reply_to_message_id=reply_to_message_id,
        )['messages'][0]['id']

    def send_audio(
            self,
            to: str | int,
            audio: str | bytes | BinaryIO,
            mime_type: str | None = None,
    ) -> str:
        """
        Send an audio file to a WhatsApp user.

        Example:

            >>> wa = WhatsApp(...)
            >>> wa.send_audio(
            ...     to='1234567890',
            ...     audio='https://example.com/audio.mp3',
            ... )

        Args:
            to: The phone ID of the WhatsApp user.
            audio: The audio file to send (either a media ID, URL, file path, bytes, or an open file object).
            mime_type: The mime type of the audio file (optional, required when sending an audio file as bytes or a file
             object, or file path that does not have an extension).

        Returns:
            The message ID of the sent audio file.
        """
        is_url, audio = resolve_media_param(wa=self, media=audio, mime_type=mime_type, filename="audio.mp3")
        return self.api.send_media(
            to=str(to),
            media_id_or_url=audio,
            is_url=is_url,
            media_type="audio",
        )['messages'][0]['id']

    def send_sticker(
            self,
            to: str | int,
            sticker: str | bytes | BinaryIO,
            mime_type: str | None = None,
    ) -> str:
        """
        Send a sticker to a WhatsApp user.
            - A static sticker needs to be 512x512 pixels and cannot exceed 100 KB.
            - An animated sticker must be 512x512 pixels and cannot exceed 500 KB.

        Example:

            >>> wa = WhatsApp(...)
            >>> wa.send_sticker(
            ...     to='1234567890',
            ...     sticker='https://example.com/sticker.webp',
            ... )

        Args:
            to: The phone ID of the WhatsApp user.
            sticker: The sticker to send (either a media ID, URL, file path, bytes, or an open file object).
            mime_type: The mime type of the sticker (optional, required when sending a sticker as bytes or a file
             object, or file path that does not have an extension).

        Returns:
            The message ID of the sent message.
        """
        is_url, sticker = resolve_media_param(wa=self, media=sticker, mime_type=mime_type, filename="sticker.webp")
        return self.api.send_media(
            to=str(to),
            media_id_or_url=sticker,
            is_url=is_url,
            media_type="sticker",
        )['messages'][0]['id']

    def send_reaction(
            self,
            to: str | int,
            emoji: str,
            message_id: str,
    ) -> str:
        """
        React to a message with an emoji.
            - You can react to incoming messages by using the :py:func:`~pywa.types.base_update.BaseUserUpdate.react` method.

        Example:

            >>> wa = WhatsApp(...)
            >>> wa.send_reaction(
            ...     to='1234567890',
            ...     emoji='👍',
            ...     message_id='wamid.XXX='
            ... )

        Args:
            to: The phone ID of the WhatsApp user.
            emoji: The emoji to react with.
            message_id: The message ID to react to.

        Returns:
            The message ID of the reaction (You can't use this message id to remove the reaction or perform any other
            action on it. instead, use the message ID of the message you reacted to).
        """
        return self.api.send_reaction(
            to=str(to),
            emoji=emoji,
            message_id=message_id,
        )['messages'][0]['id']

    def remove_reaction(
            self,
            to: str | int,
            message_id: str,
    ) -> str:
        """
        Remove a reaction from a message.
            - You can remove reactions from incoming messages by using the :py:func:`~pywa.types.base_update.BaseUserUpdate.unreact` method.

        Example:

            >>> wa = WhatsApp(...)
            >>> wa.remove_reaction(
            ...     to='1234567890',
            ...     message_id='wamid.XXX='
            ... )

        Returns:
            The message ID of the reaction (You can't use this message id to re-react or perform any other action on it.
            instead, use the message ID of the message you unreacted to).
        """
        return self.api.send_reaction(
            to=str(to),
            emoji="",
            message_id=message_id
        )['messages'][0]['id']

    def send_location(
            self,
            to: str | int,
            latitude: float,
            longitude: float,
            name: str | None = None,
            address: str | None = None,
    ) -> str:
        """
        Send a location to a WhatsApp user.

        Example:

            >>> wa = WhatsApp(...)
            >>> wa.send_location(
            ...     to='1234567890',
            ...     latitude=37.4847483695049,
            ...     longitude=--122.1473373086664,
            ...     name='WhatsApp HQ',
            ...     address='Menlo Park, 1601 Willow Rd, United States',
            ... )

        Args:
            to: The phone ID of the WhatsApp user.
            latitude: The latitude of the location.
            longitude: The longitude of the location.
            name: The name of the location (optional).
            address: The address of the location (optional).

        Returns:
            The message ID of the sent location.
        """
        return self.api.send_location(
            to=str(to),
            latitude=latitude,
            longitude=longitude,
            name=name,
            address=address,
        )['messages'][0]['id']

    def send_contact(
            self,
            to: str | int,
            contact: Contact | Iterable[Contact],
            reply_to_message_id: str | None = None,
    ) -> str:
        """
        Send a contact/s to a WhatsApp user.

        Example:

            >>> from pywa.types import Contact
            >>> wa = WhatsApp(...)
            >>> wa.send_contact(
            ...     to='1234567890',
            ...     contact=Contact(
            ...         name=Contact.Name(formatted_name='David Lev', first_name='David'),
            ...         phones=[Contact.Phone(phone='1234567890', wa_id='1234567890', type='MOBILE')],
            ...         emails=[Contact.Email(email='test@test.com', type='WORK')],
            ...         urls=[Contact.Url(url='https://exmaple.com', type='HOME')],
            ...      )
            ... )

        Args:
            to: The phone ID of the WhatsApp user.
            contact: The contact/s to send.
            reply_to_message_id: The message ID to reply to (optional).

        Returns:
            The message ID of the sent message.
        """
        return self.api.send_contacts(
            to=str(to),
            contacts=tuple(c.to_dict() for c in contact) if isinstance(contact, Iterable) else (contact.to_dict()),
            reply_to_message_id=reply_to_message_id,
        )['messages'][0]['id']

    def send_catalog(
            self,
            to: str | int,
            body: str,
            footer: str | None = None,
            thumbnail_product_sku: str | None = None,
            reply_to_message_id: str | None = None,
    ) -> str:
        """
        Send the business catalog to a WhatsApp user.

        Example:

            >>> wa = WhatsApp(...)
            >>> wa.send_catalog(
            ...     to='1234567890',
            ...     body='Check out our catalog!',
            ...     footer='Powered by PyWa',
            ...     thumbnail_product_sku='SKU123',
            ... )

        Args:
            to: The phone ID of the WhatsApp user.
            body: Text to appear in the message body (up to 1024 characters).
            footer: Text to appear in the footer of the message (optional, up to 60 characters).
            thumbnail_product_sku: The thumbnail of this item will be used as the message's header image (optional, if
                not provided, the first item in the catalog will be used).
            reply_to_message_id: The message ID to reply to (optional).

        Returns:
            The message ID of the sent message.
        """
        return self.api.send_interactive_message(
            to=str(to),
            type_="catalog_message",
            action={
                "name": "catalog_message",
                **({"parameters": {
                    "thumbnail_product_retailer_id": thumbnail_product_sku,
                }} if thumbnail_product_sku else {}),
            },
            body=body,
            footer=footer,
            reply_to_message_id=reply_to_message_id
        )['messages'][0]['id']

    def send_product(
            self,
            to: str | int,
            catalog_id: str,
            sku: str,
            body: str | None = None,
            footer: str | None = None,
            reply_to_message_id: str | None = None,
    ) -> str:
        """
        Send a product from a business catalog to a WhatsApp user.
            - To send multiple products, use :py:func:`~pywa.client.WhatsApp.send_products`.

        Example:

            >>> wa = WhatsApp(...)
            >>> wa.send_product(
            ...     to='1234567890',
            ...     catalog_id='1234567890',
            ...     sku='SKU123',
            ...     body='Check out this product!',
            ...     footer='Powered by PyWa',
            ... )

        Args:
            to: The phone ID of the WhatsApp user.
            catalog_id: The ID of the catalog to send the product from. (To get the catalog ID use
             :py:func:`~pywa.client.WhatsApp.get_commerce_settings` or in the `Commerce Manager
             <https://business.facebook.com/commerce/>`_).
            sku: The product SKU to send.
            body: Text to appear in the message body (up to 1024 characters).
            footer: Text to appear in the footer of the message (optional, up to 60 characters).
            reply_to_message_id: The message ID to reply to (optional).

        Returns:
            The message ID of the sent message.
        """
        return self.api.send_interactive_message(
            to=str(to),
            type_="product",
            action={
                "catalog_id": catalog_id,
                "product_retailer_id": sku,
            },
            body=body,
            footer=footer,
            reply_to_message_id=reply_to_message_id
        )['messages'][0]['id']

    def send_products(
            self,
            to: str | int,
            catalog_id: str,
            product_sections: Iterable[ProductsSection],
            title: str,
            body: str,
            footer: str | None = None,
            reply_to_message_id: str | None = None,
    ) -> str:
        """
        Send products from a business catalog to a WhatsApp user.
            - To send a single product, use :py:func:`~pywa.client.WhatsApp.send_product`.

        Example:

            >>> from pywa.types import ProductsSection
            >>> wa = WhatsApp(...)
            >>> wa.send_products(
            ...     to='1234567890',
            ...     catalog_id='1234567890',
            ...     title='Tech Products',
            ...     body='Check out our products!',
            ...     product_sections=[
            ...         ProductsSection(
            ...             title='Smartphones',
            ...             skus=['IPHONE12', 'GALAXYS21'],
            ...         ),
            ...         ProductsSection(
            ...             title='Laptops',
            ...             skus=['MACBOOKPRO', 'SURFACEPRO'],
            ...         ),
            ...     ],
            ...     footer='Powered by PyWa',
            ... )

        Args:
            to: The phone ID of the WhatsApp user.
            catalog_id: The ID of the catalog to send the product from (To get the catalog ID use
             :py:func:`~pywa.client.WhatsApp.get_commerce_settings` or in the `Commerce Manager
             <https://business.facebook.com/commerce/>`_).
            product_sections: The product sections to send (up to 30 products across all sections).
            title: The title of the product list (up to 60 characters).
            body: Text to appear in the message body (up to 1024 characters).
            footer: Text to appear in the footer of the message (optional, up to 60 characters).
            reply_to_message_id: The message ID to reply to (optional).

        Returns:
            The message ID of the sent message.
        """
        return self.api.send_interactive_message(
            to=str(to),
            type_="product_list",
            action={
                "catalog_id": catalog_id,
                "sections": tuple(ps.to_dict() for ps in product_sections),
            },
            header={"type": "text", "text": title},
            body=body,
            footer=footer,
            reply_to_message_id=reply_to_message_id
        )['messages'][0]['id']

    def mark_message_as_read(
            self,
            message_id: str,
    ) -> bool:
        """
        Mark a message as read.
            - You can mark incoming messages as read by using the :py:func:`~pywa.types.base_update.BaseUserUpdate.mark_as_read` method.

        Example:

            >>> wa = WhatsApp(...)
            >>> wa.mark_message_as_read(message_id='wamid.XXX=')

        Args:
            message_id: The message ID to mark as read.

        Returns:
            Whether the message was marked as read.
        """
        return self.api.mark_message_as_read(message_id=message_id)['success']

    def upload_media(
            self,
            media: str | bytes | BinaryIO,
            mime_type: str,
            filename: str | None = None,
    ) -> str:
        """
        Upload media to WhatsApp servers.

        Example:

            >>> wa = WhatsApp(...)
            >>> wa.upload_media(
            ...     media='https://example.com/image.jpg',
            ...     mime_type='image/jpeg',
            ... )

        Args:
            media: The media to upload (can be a URL, bytes, or a file path).
            mime_type: The MIME type of the media (required if media is bytes or a file path).
            filename: The file name of the media (required if media is bytes).

        Returns:
            The media ID.

        Raises:
            ValueError: If the file is not found or the URL is invalid or if the media is bytes and the filename is not
             provided.
        """
        if isinstance(media, str):
            if os.path.isfile(media):
                file, filename, mime_type = \
                    open(media, 'rb'), os.path.basename(media), (mimetypes.guess_type(media)[0] or mime_type)
            elif media.startswith(("https://", "http://")):
                res = requests.get(media)
                res.raise_for_status()
                file, filename, mime_type = \
                    res.content, os.path.basename(media) or filename, (res.headers['Content-Type'] or mime_type)
            else:
                raise ValueError(f'File not found or invalid URL: {media}')
        else:
            file = media
            if filename is None:
                raise ValueError('filename is required if media is bytes')
        return self.api.upload_media(
            filename=filename,
            media=file,
            mime_type=mime_type,
        )['id']

    def get_media_url(
            self,
            media_id: str
    ) -> MediaUrlResponse:
        """
        Get the URL of a media.
            - The URL is valid for 5 minutes.
            - The media can be downloaded directly from the message using the :py:func:`~pywa.types.Message.download_media` method.

        Example:

            >>> wa = WhatsApp(...)
            >>> wa.get_media_url(media_id='wamid.XXX=')

        Args:
            media_id: The media ID.

        Returns:
            A MediaResponse object with the media URL.
        """
        res = self.api.get_media_url(media_id=media_id)
        return MediaUrlResponse(
            _client=self,
            id=res['id'],
            url=res['url'],
            mime_type=res['mime_type'],
            sha256=res['sha256'],
            file_size=res['file_size'],
        )

    def download_media(
            self,
            url: str,
            path: str | None = None,
            filename: str | None = None,
            in_memory: bool = False,
    ) -> str | bytes:
        """
        Download a media file from WhatsApp servers.

        Example:

            >>> wa = WhatsApp(...)
            >>> wa.download_media(
            ...     url='https://mmg-fna.whatsapp.net/d/f/Amc.../v2/1234567890',
            ...     path='/home/david/Downloads',
            ...     filename='image.jpg',
            ... )

        Args:
            url: The URL of the media file (from :py:func:`~pywa.client.WhatsApp.get_media_url`).
            path: The path where to save the file (if not provided, the current working directory will be used).
            filename: The name of the file (if not provided, it will be guessed from the URL + extension).
            in_memory: Whether to return the file as bytes instead of saving it to disk (default: False).

        Returns:
            The path of the saved file if ``in_memory`` is False, the file as bytes otherwise.
        """
        content, mimetype = self.api.get_media_bytes(media_url=url)
        if in_memory:
            return content
        if path is None:
            path = os.getcwd()
        if filename is None:
            filename = hashlib.sha256(url.encode()).hexdigest() + mimetypes.guess_extension(mimetype) or '.bin'
        path = os.path.join(path, filename)
        with open(path, "wb") as f:
            f.write(content)
        return path

    def get_business_profile(self) -> BusinessProfile:
        """
        Get the business profile of the WhatsApp Business account.

        Example:

            >>> wa = WhatsApp(...)
            >>> wa.get_business_profile()

        Returns:
            The business profile.
        """
        return BusinessProfile.from_dict(data=self.api.get_business_profile()['data'][0])

    def update_business_profile(
            self,
            about: str | None = _MISSING,
            address: str | None = _MISSING,
            description: str | None = _MISSING,
            email: str | None = _MISSING,
            profile_picture_handle: str | None = _MISSING,
            industry: Industry | None = _MISSING,
            websites: Iterable[str] | None = _MISSING
    ) -> bool:
        """
        Update the business profile of the WhatsApp Business account.

        Example:

            >>> from pywa.types import Industry
            >>> wa = WhatsApp(...)
            >>> wa.update_business_profile(
            ...     about='This is a test business',
            ...     address='Menlo Park, 1601 Willow Rd, United States',
            ...     description='This is a test business',
            ...     email='test@test.com',
            ...     profile_picture_handle='1234567890',
            ...     industry=Industry.NOT_A_BIZ,
            ...     websites=('https://example.com', 'https://google.com'),
            ... )

        Args:
            about: The business's About text. This text appears in the business's profile, beneath its profile image,
             phone number, and contact buttons. (cannot be empty. must be between 1 and 139 characters. `markdown
             <https://faq.whatsapp.com/539178204879377>`_ is not supported. Hyperlinks can be included but
             will not render as clickable links.)
            address: Address of the business. Character limit 256.
            description: Description of the business. Character limit 512.
            email: The contact email address (in valid email format) of the business. Character limit 128.
            profile_picture_handle: Handle of the profile picture. This handle is generated when you upload the binary
             file for the profile picture to Meta using the `Resumable Upload API
             <https://developers.facebook.com/docs/graph-api/guides/upload>`_.
            industry: Industry of the business.
            websites: The URLs associated with the business. For instance, a website, Facebook Page, or Instagram.
             (You must include the ``http://`` or ``https://`` portion of the URL.
             There is a maximum of 2 websites with a maximum of 256 characters each.)

        Returns:
            Whether the business profile was updated.
        """
        data = {
            key: value or '' for key, value in {
                'about': about,
                'address': address,
                'description': description,
                'email': email,
                'profile_picture_handle': profile_picture_handle,
                'vertical': industry,
                'websites': websites,
            }.items() if value is not _MISSING
        }
        return self.api.update_business_profile(data)['success']

    def get_commerce_settings(self) -> CommerceSettings:
        """
        Get the commerce settings of the WhatsApp Business account.

        Example:

            >>> wa = WhatsApp(...)
            >>> wa.get_commerce_settings()

        Returns:
            The commerce settings.
        """
        return CommerceSettings.from_dict(data=self.api.get_commerce_settings()['data'][0])

    def update_commerce_settings(
            self,
            is_catalog_visible: bool = None,
            is_cart_enabled: bool = None,
    ) -> bool:
        """
        Update the commerce settings of the WhatsApp Business account.

        Example:

            >>> wa = WhatsApp(...)
            >>> wa.update_commerce_settings(
            ...     is_catalog_visible=True,
            ...     is_cart_enabled=True,
            ... )

        Args:
            is_catalog_visible: Whether the catalog is visible (optional).
            is_cart_enabled: Whether the cart is enabled (optional).

        Returns:
            Whether the commerce settings were updated.

        Raises:
            ValueError: If no arguments are provided.
        """
        data = {
            key: value for key, value in {
                'is_cart_enabled': is_cart_enabled,
                'is_catalog_visible': is_catalog_visible,
            }.items() if value is not None
        }
        if not data:
            raise ValueError('At least one argument must be provided')
        return self.api.update_commerce_settings(data)['success']

    def _validate_business_account_id_provided(self):
        """Internal method to validate that the business account ID was provided."""
        if self.business_account_id is None:
            raise ValueError(
                "You must provide the business account ID when using this method. "
                "You can provide it when initializing the client or by setting the business_account_id attribute."
            )

    def create_template(
            self,
            template: NewTemplate,
            placeholder: tuple[str, str] | None = None,
    ) -> TemplateResponse:
        """
        `\`Create Templates\` on developers.facebook.com
        <https://developers.facebook.com/docs/whatsapp/business-management-api/message-templates>`_.

        - To send a template, use :py:func:`~pywa.client.WhatsApp.send_template`.

        ATTENTION: In case of an errors, WhatsApp does not return a proper error message, instead, it returns a message
        of `invalid parameter` with error code of 100. You need to pay attention to the following:

        - The template name must be unique.
        - The limitiations of the characters in every field (all documented).
        - The order of the buttons.


        Templates can be created and managed in the
        `WhatsApp Message Templates <https://business.facebook.com/wa/manage/message-templates/>`_ dashboard.

        Example:

            >>> from pywa.types import NewTemplate as NewTemp
            >>> wa = WhatsApp(...)
            >>> wa.create_template(
            ...     template=NewTemp(
            ...         name='buy_new_iphone_x',
            ...         category=NewTemp.Category.MARKETING,
            ...         language=NewTemp.Language.ENGLISH_US,
            ...         header=NewTemp.Text('The New iPhone {15} is here!'),
            ...         body=NewTemp.Body('Buy now and use the code {WA_IPHONE_15} to get {15%} off!'),
            ...         footer=NewTemp.Footer('Powered by PyWa'),
            ...         buttons=[
            ...             NewTemp.UrlButton(title='Buy Now', url='https://example.com/shop/{iphone15}'),
            ...             NewTemp.PhoneNumberButton(title='Call Us', phone_number='1234567890'),
            ...             NewTemp.QuickReplyButton('Unsubscribe from marketing messages'),
            ...             NewTemp.QuickReplyButton('Unsubscribe from all messages'),
            ...         ],
            ...     ),
            ... )

        Example for Authentication Template:

            >>> from pywa.types import NewTemplate as NewTemp
            >>> wa = WhatsApp(...)
            >>> wa.create_template(
            ...     template=NewTemp(
            ...         name='auth_with_otp',
            ...         category=NewTemp.Category.AUTHENTICATION,
            ...         language=NewTemp.Language.ENGLISH_US,
            ...         body=NewTemp.AuthBody(
            ...             code_expiration_minutes=5,
            ...             add_security_recommendation=True,
            ...         ),
            ...         buttons=NewTemp.OTPButton(
            ...             otp_type=NewTemp.OTPButton.OtpType.ONE_TAP,
            ...             title='Copy Code',
            ...             autofill_text='Autofill',
            ...             package_name='com.example.app',
            ...             signature_hash='1234567890ABCDEF1234567890ABCDEF12345678'
            ...         )
            ...     ),
            ... )

        Args:
            template: The template to create.
             <https://developers.facebook.com/docs/whatsapp/business-management-api/message-templates/supported-languages>`_).
            placeholder: The placeholders start & end (optional, default: ``('{', '}')``)).

        Returns:
            The template created response. containing the template ID, status and category.
        """
        self._validate_business_account_id_provided()
        return TemplateResponse(**self.api.create_template(
            business_account_id=self.business_account_id,
            template=template.to_dict(placeholder=placeholder)
        ))

    def send_template(
            self,
            to: str | int,
            template: Template,
            reply_to_message_id: str | None = None,
    ) -> str:
        """
        Send a template to a WhatsApp user.

        - To create a template, use :py:func:`~pywa.client.WhatsApp.create_template`.

        Example:

            >>> from pywa.types import Template as Temp
            >>> wa = WhatsApp(...)
            >>> wa.send_template(
            ...     to='1234567890',
            ...         template=Temp(
            ...         name='buy_new_iphone_x',
            ...         language=Temp.Language.ENGLISH_US,
            ...         header=Temp.TextValue(value='15'),
            ...         body=[
            ...             Temp.TextValue(value='John Doe'),
            ...             Temp.TextValue(value='WA_IPHONE_15'),
            ...             Temp.TextValue(value='15%'),
            ...         ],
            ...         buttons=[
            ...             Temp.UrlButtonValue(value='iphone15'),
            ...             Temp.QuickReplyButtonData(data='unsubscribe_from_marketing_messages'),
            ...             Temp.QuickReplyButtonData(data='unsubscribe_from_all_messages'),
            ...         ],
            ...     ),
            ... )

        Example for Authentication Template:

            >>> from pywa.types import Template as Temp
            >>> wa = WhatsApp(...)
            >>> wa.send_template(
            ...     to='1234567890',
            ...         template=Temp(
            ...         name='auth_with_otp',
            ...         language=Temp.Language.ENGLISH_US,
            ...         buttons=Temp.OTPButtonCode(code='123456'),
            ...     ),
            ... )

        Args:
            to: The phone ID of the WhatsApp user.
            template: The template to send.
            reply_to_message_id: The message ID to reply to (optional).

        Returns:
            The message ID of the sent template.

        Raises:

        """
        is_url = None
        match type(template.header):
            case Template.TextValue:
                pass
            case Template.Image:
                is_url, template.header.image = resolve_media_param(
                    wa=self, media=template.header.image, mime_type="image/jpeg", filename="image.jpg"
                )
            case Template.Document:
                is_url, template.header.document = resolve_media_param(
                    wa=self, media=template.header.document, mime_type="text/plain", filename="file.pdf"
                )
            case Template.Video:
                is_url, template.header.video = resolve_media_param(
                    wa=self, media=template.header.video, mime_type="video/mp4", filename="video.mp4"
                )
        return self.api.send_template(
            to=str(to),
            template=template.to_dict(is_header_url=is_url),
            reply_to_message_id=reply_to_message_id,
        )['messages'][0]['id']
