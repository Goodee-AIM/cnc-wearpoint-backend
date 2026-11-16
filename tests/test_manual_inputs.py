import asyncio
import base64
import os
import tempfile
import unittest
from unittest.mock import patch

import httpx
from fastapi import FastAPI
from app.api.routers.manual_inputs import router

CSV = b'0,1,2,3,4,2023-01-01 00:00:00.000000000\n1,2,3,4,5,2023-01-01 00:00:01.000000000\n'
PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')

class ManualInputTests(unittest.TestCase):
    def test_upload_reload_and_original_files(self):
        async def check():
            app = FastAPI(); app.include_router(router)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
                payload = dict(image_name='../tool.png', sensor_name='sensor.csv', image_base64=base64.b64encode(PNG).decode(), sensor_base64=base64.b64encode(CSV).decode())
                result = await client.post('/api/manual-inputs', json=payload)
                self.assertEqual(result.status_code, 201, result.text)
                item = result.json()
                self.assertEqual(item['row_count'], 2)
                self.assertEqual(item['image_name'], 'tool.png')
                self.assertIsNone(item['predicted_wear'])
                self.assertEqual((await client.get(item['image_url'])).content, PNG)
                self.assertEqual((await client.get(item['sensor_url'])).content, CSV)
            app = FastAPI(); app.include_router(router)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
                self.assertEqual((await client.get('/api/manual-inputs')).json()['items'][0]['id'], item['id'])
                payload['sensor_base64'] = base64.b64encode(b'0,1,2\n').decode()
                self.assertEqual((await client.post('/api/manual-inputs', json=payload)).status_code, 422)
                self.assertEqual(len((await client.get('/api/manual-inputs')).json()['items']), 1)
                self.assertEqual((await client.get('/api/manual-inputs/not-an-id')).status_code, 404)
        with tempfile.TemporaryDirectory() as path, patch.dict(os.environ, MANUAL_INPUT_ROOT=path):
            asyncio.run(check())

    def test_bad_numbers_times_and_empty_uploads(self):
        from app.api.routers.manual_inputs import validate_csv
        from fastapi import HTTPException
        for value in [b'', b'NaN,1,2,3,4,2023-01-01 00:00:00\n', b'0,1,2,3,4,2023-02-30 00:00:00\n', CSV.splitlines()[1] + b'\n' + CSV.splitlines()[0]]:
            with self.assertRaises(HTTPException): validate_csv(value)

if __name__ == '__main__': unittest.main()
