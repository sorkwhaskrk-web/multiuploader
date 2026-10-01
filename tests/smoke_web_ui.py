"""Real Chrome smoke test using fictitious settings in a temporary directory.

Run manually: python tests/smoke_web_ui.py. Screenshots stay under ignored data/.
"""

import threading
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

from shorts_distributor.web import Dashboard, make_server
from shorts_distributor.web_settings import ROOT, write_json


def main():
    with TemporaryDirectory() as tmp:
        app = Dashboard(Path(tmp))
        server = make_server(app, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        errors = []
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width":1440,"height":1100})
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(f"http://127.0.0.1:{server.server_port}")
                page.wait_for_function("() => document.querySelector('#mode').textContent === '준비 모드'")
                assert page.locator("#publish-button").is_disabled()
                assert page.locator("#discover").is_disabled()
                page.get_by_role("button", name="계정 및 설정", exact=False).first.click()
                page.locator('[name="YOUTUBE_HANDLE"]').fill("@example-channel")
                page.locator('[name="target"][value="instagram"]').check()
                page.locator('[name="target"][value="tiktok"]').check()
                page.locator('[name="INSTAGRAM_HANDLE"]').fill("example_creator")
                page.get_by_role("button",name="설정 저장 →").click()
                page.wait_for_function("() => document.querySelector('#save-state').textContent.startsWith('저장됨')")
                assert (Path(tmp)/".env").is_file()
                page.get_by_role("button",name="배포 작업",exact=False).first.click()
                assert page.locator("#discover").is_enabled()
                page.locator("#video-ids").fill("abcdefghijk,lmnopqrstuv")
                page.locator("#apply-ids").click()
                assert page.locator("#selected-count").inner_text()=="2편"
                assert page.locator("#cell-count").inner_text()=="4개"
                assert page.locator("#preview-button").is_enabled()
                page.locator("#targets input").first.uncheck()
                assert page.locator("#cell-count").inner_text()=="2개"
                page.locator("#targets input").first.check()

                # Feed a persisted fictitious preview through the real history API.
                directory=app.jobs_dir/("a"*32)
                write_json(directory/"meta.json",{"id":directory.name,"action":"preview","status":"succeeded","created_at":"2026-10-01T00:00:00+00:00"})
                write_json(directory/"snapshot.json",{})
                write_json(directory/"result.json",{
                    "target_platforms":["instagram","tiktok"],
                    "batch_oldest_first":[{"youtube_id":"abcdefghijk","title":"<script>window.unsafe = true</script>","post_text":"첫 번째 영상의 게시 문구\n#example","upload_date":"20260901","codec":"h264"}],
                    "cells":[{"youtube_id":"abcdefghijk","platform":"instagram","status":"planned"},{"youtube_id":"abcdefghijk","platform":"tiktok","status":"skipped-policy","hint":"example rule"}],
                })
                page.get_by_role("button",name="작업 기록",exact=False).first.click()
                page.get_by_role("button",name="결과 보기 ↗").first.click()
                page.wait_for_function("() => document.querySelector('#preview-label').textContent === '검토 가능'")
                assert page.locator(".post-text").inner_text()=="첫 번째 영상의 게시 문구\n#example"
                assert page.locator(".cell").count()==2
                assert page.evaluate("window.unsafe === undefined")
                assert page.locator("#publish-button").is_disabled()
                out=ROOT/"data"/"web"/"qa";out.mkdir(parents=True,exist_ok=True)
                page.screenshot(path=str(out/"desktop.png"),full_page=True)
                page.set_viewport_size({"width":390,"height":844})
                assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
                page.screenshot(path=str(out/"mobile.png"),full_page=True)
                page.get_by_role("button",name="사용 가이드",exact=False).first.click()
                assert page.locator("#view-guide").is_visible()
                assert not errors, errors
                browser.close()
            # Publishing mode confirmation is tested only against a fixture server.
            app.allow_publish = True
            with sync_playwright() as p:
                browser=p.chromium.launch(channel="chrome",headless=True)
                page=browser.new_page(viewport={"width":1280,"height":900})
                page.goto(f"http://127.0.0.1:{server.server_port}")
                page.wait_for_function("() => document.querySelector('#mode').textContent === '게시 모드'")
                page.get_by_role("button",name="작업 기록",exact=False).first.click()
                page.get_by_role("button",name="결과 보기 ↗").first.click()
                page.wait_for_function("() => !document.querySelector('#publish-button').disabled")
                page.locator("#publish-button").click()
                assert page.locator("#publish-dialog").is_visible()
                page.locator("#confirm-publish").click()
                assert page.locator("#publish-dialog").is_visible()
                page.get_by_role("button",name="돌아가기").click()
                assert not page.locator("#publish-dialog").is_visible()
                browser.close()
            print("Chrome UI smoke test: settings, selection, preview, history, XSS, mobile layout PASS")
        finally:
            server.shutdown();server.server_close();thread.join()


if __name__ == "__main__":
    main()
