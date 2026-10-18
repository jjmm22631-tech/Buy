import asyncio
import unittest

from bot import _handle_healthcheck, healthcheck_response
from handlers.start import DEFAULT_WELCOME, welcome_with_code_prompt
from keyboards import admin_menu, main_menu, movie_menu
from aiogram.types import ReplyKeyboardMarkup, ReplyKeyboardRemove


class HealthcheckTests(unittest.TestCase):
    def test_root_and_health_paths_return_ok(self) -> None:
        for request_line in (b"GET / HTTP/1.1\r\n", b"GET /health HTTP/1.1\r\n", b"GET /health?source=render HTTP/1.1\r\n"):
            with self.subTest(request_line=request_line):
                self.assertEqual(healthcheck_response(request_line), (200, b"ok\n"))

    def test_unknown_paths_and_methods_are_not_found(self) -> None:
        for request_line in (b"GET /missing HTTP/1.1\r\n", b"POST /health HTTP/1.1\r\n", b"invalid request\r\n"):
            with self.subTest(request_line=request_line):
                self.assertEqual(healthcheck_response(request_line), (404, b"not found\n"))

    def test_start_welcome_always_requests_a_movie_code_without_duplicating_it(self) -> None:
        self.assertEqual(welcome_with_code_prompt("Salom"), "Salom\n\n🎬 Kino kodini yuboring.")
        self.assertEqual(welcome_with_code_prompt(DEFAULT_WELCOME), DEFAULT_WELCOME)

    def test_second_bot_admin_menus_remain_visible(self) -> None:
        self.assertIsInstance(main_menu(is_admin=True), ReplyKeyboardMarkup)
        self.assertIsInstance(admin_menu(), ReplyKeyboardMarkup)
        self.assertIsInstance(movie_menu(), ReplyKeyboardMarkup)
        self.assertIsInstance(main_menu(is_admin=False, hide_keyboard=True), ReplyKeyboardRemove)


class HealthcheckServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_endpoint_returns_http_response(self) -> None:
        server = await asyncio.start_server(_handle_healthcheck, host="127.0.0.1", port=0)
        try:
            port = server.sockets[0].getsockname()[1]
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(b"GET /health HTTP/1.1\r\nHost: localhost\r\n\r\n")
            await writer.drain()
            response = await reader.read()
            writer.close()
            await writer.wait_closed()
            self.assertIn(b"HTTP/1.1 200 OK\r\n", response)
            self.assertTrue(response.endswith(b"ok\n"))
        finally:
            server.close()
            await server.wait_closed()


if __name__ == "__main__":
    unittest.main()
