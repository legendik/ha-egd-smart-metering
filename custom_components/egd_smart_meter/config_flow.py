"""Config flow for EGD Smart Meter integration."""

from __future__ import annotations

from datetime import date
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

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
        self._ean: str = ""

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
                    vol.Required(CONF_CLIENT_ID): cv.string,
                    vol.Required(CONF_CLIENT_SECRET): cv.string,
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
            self._ean = user_input[CONF_EAN]
            return await self.async_step_date()

        return self.async_show_form(
            step_id="ean",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EAN): cv.string,
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
            date_str = user_input.get(CONF_START_DATE, "")
            try:
                start_date = date.fromisoformat(date_str)
            except ValueError:
                return self.async_show_form(
                    step_id="date",
                    data_schema=vol.Schema(
                        {
                            vol.Required(
                                CONF_START_DATE,
                                default=(date.today().replace(day=1)).isoformat(),
                            ): cv.string,
                        }
                    ),
                    errors={"base": "invalid_date"},
                )

            return self.async_create_entry(
                title=f"EGD {self._ean}",
                data={
                    CONF_CLIENT_ID: self._client_id,
                    CONF_CLIENT_SECRET: self._client_secret,
                    CONF_EAN: self._ean,
                    CONF_START_DATE: start_date,
                },
            )

        default_date = (date.today().replace(day=1)).isoformat()

        return self.async_show_form(
            step_id="date",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_START_DATE, default=default_date): cv.string,
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
            date_str = user_input.get(CONF_START_DATE, "")
            try:
                start_date = date.fromisoformat(date_str)
            except ValueError:
                return self.async_show_form(
                    step_id="init",
                    data_schema=vol.Schema(
                        {
                            vol.Required(
                                CONF_START_DATE,
                                default=self._config_entry.data.get(CONF_START_DATE, "")
                                if isinstance(self._config_entry.data.get(CONF_START_DATE), date)
                                else str(self._config_entry.data.get(CONF_START_DATE, "")),
                            ): cv.string,
                        }
                    ),
                    errors={"base": "invalid_date"},
                )

            return self.async_create_entry(
                title="",
                data={CONF_START_DATE: start_date},
            )

        current_date = self._config_entry.data.get(CONF_START_DATE, "")
        if isinstance(current_date, date):
            current_date = current_date.isoformat()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_START_DATE, default=current_date): cv.string,
                }
            ),
        )
