"""Config flow for EGD Smart Meter integration."""

from __future__ import annotations

from datetime import date
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .api import EGDAuthError, EGDClient
from .const import (
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET,
    CONF_EAN,
    CONF_START_DATE,
    DOMAIN,
    LOGGER,
)


class EGDConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EGD Smart Meter."""

    VERSION = 1

    def __init__(self) -> None:
        self._client_id: str = ""
        self._client_secret: str = ""

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle OAuth2 credentials."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._client_id = user_input[CONF_CLIENT_ID]
            self._client_secret = user_input[CONF_CLIENT_SECRET]

            client = EGDClient(self._client_id, self._client_secret)
            try:
                await client._get_access_token()
                await client.close()
            except EGDAuthError:
                errors["base"] = "auth"
            except Exception:
                LOGGER.exception("Authentication error")
                errors["base"] = "unknown"
            else:
                return await self.async_step_ean()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CLIENT_ID): str,
                    vol.Required(CONF_CLIENT_SECRET): str,
                }
            ),
            errors=errors,
        )

    async def async_step_ean(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle EAN input."""
        if user_input is not None:
            return await self.async_step_date(user_input)

        return self.async_show_form(
            step_id="ean",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EAN): str,
                }
            ),
            description_placeholders={
                "description": "Enter the EAN (Energy Identification Number) of your metering point."
            },
        )

    async def async_step_date(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle start date."""
        if user_input is not None:
            return self.async_create_entry(
                title=f"EGD {user_input[CONF_EAN]}",
                data={
                    CONF_CLIENT_ID: self._client_id,
                    CONF_CLIENT_SECRET: self._client_secret,
                    CONF_EAN: user_input[CONF_EAN],
                    CONF_START_DATE: user_input[CONF_START_DATE],
                },
            )

        default_date = (date.today().replace(day=1)).isoformat()

        return self.async_show_form(
            step_id="date",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EAN): str,
                    vol.Required(CONF_START_DATE, default=default_date): vol.Coerce(
                        date.fromisoformat
                    ),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> OptionsFlow:
        """Get the options flow."""
        return EGDOptionsFlow(config_entry)


class EGDOptionsFlow(OptionsFlow):
    """Handle options flow."""

    def __init__(self, config_entry: Any) -> None:
        self._config_entry = config_entry

    async def async_step_init(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_START_DATE,
                        default=self._config_entry.data.get(CONF_START_DATE),
                    ): vol.Coerce(date.fromisoformat),
                }
            ),
        )
