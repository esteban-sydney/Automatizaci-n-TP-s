from playwright.async_api import async_playwright
from config import *
from queue import Queue
texto_bitacora = ""
cola_telegram = Queue()
# =========================================
# INICIAR TP
# =========================================
async def iniciar_tp(datos):

    print("INICIANDO TP...")
    print(datos)

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            channel="msedge",
            headless=False,
            args=[
                "--start-maximized"
            ]
        )

        context = await browser.new_context(
            no_viewport=True
        )

        page = await context.new_page()

        # LOGIN
        await page.goto(SITIO["url"])

        await page.fill(
            SITIO["selector_user"],
            USUARIO_PORTAL
        )

        await page.fill(
            SITIO["selector_pass"],
            PASSWORD_PORTAL
        )

        await page.click(
            SITIO["selector_btn_login"]
        )

        await page.wait_for_timeout(5000)

        print("LOGIN OK")

        await page.wait_for_timeout(10000)

        await browser.close()


# =========================================
# CERRAR TP
# =========================================
async def cerrar_tp(datos):

    print("CERRANDO TP...")
    print(datos)

    async with async_playwright() as p:

        browser = await p.chromium.launch(
            channel="msedge",
            headless=False,
            args=[
                "--start-maximized"
            ]
        )

        context = await browser.new_context(
            no_viewport=True
        )

        page = await context.new_page()

        # LOGIN
        await page.goto(SITIO["url"])

        await page.fill(
            SITIO["selector_user"],
            USUARIO_PORTAL
        )

        await page.fill(
            SITIO["selector_pass"],
            PASSWORD_PORTAL
        )

        await page.click(
            SITIO["selector_btn_login"]
        )

        await page.wait_for_timeout(5000)

        print("LOGIN OK")

        await page.wait_for_timeout(10000)

        await browser.close()