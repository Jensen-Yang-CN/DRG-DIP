import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from server import DemoHandler


class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), DemoHandler)
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_catalog_and_group_api(self):
        with urlopen(self.url + "/api/catalog") as response:
            catalog = json.load(response)
        self.assertEqual(catalog["coreCount"], 5125)
        self.assertTrue(any(item["code"] == "J18.9" for item in catalog["suggestions"]["dx"]))

        request = Request(
            self.url + "/api/group",
            data=json.dumps({"diagnoses": ["J18.900"], "operations": ["33.2402"]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request) as response:
            result = json.load(response)
        self.assertEqual(result["hit"]["key"], "BX-774")
        self.assertEqual(result["sourceSheetName"], "二、并项规则下的核心病种")

    def test_pages_and_logo(self):
        for path in ("/", "/index.html", "/flow.html", "/assets/pku-logo.png", "/app.js?v=public"):
            with self.subTest(path=path), urlopen(self.url + path) as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers["Cache-Control"], "no-cache")

    def test_only_public_pages_and_assets_are_served(self):
        for path in ("/server.py", "/grouping.py", "/data/rules.json", "/assets/", "/README.md"):
            with self.subTest(path=path):
                with self.assertRaises(HTTPError) as error:
                    urlopen(self.url + path)
                self.assertEqual(error.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
