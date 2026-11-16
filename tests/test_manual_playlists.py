import base64
import os
import tempfile
import unittest
from unittest.mock import patch

try:
    import httpx2 as httpx
except ImportError:
    import httpx
from fastapi import FastAPI
from app.api.routers.manual_inputs import router


class ManualPlaylistTests(unittest.IsolatedAsyncioTestCase):
    async def test_playlist_order_persistence_and_invalid_members(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, MANUAL_INPUT_ROOT=folder):
            app = FastAPI(); app.include_router(router)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://test') as client:
                csv = b'1,2,3,4,5,2023-01-01 00:00:00\n2,3,4,5,6,2023-01-01 00:00:01\n'
                payload = dict(image_name='tool.png',sensor_name='tool.csv',image_base64=base64.b64encode(b'\x89PNG\r\n\x1a\n').decode(),sensor_base64=base64.b64encode(csv).decode())
                records = [(await client.post('/api/manual-inputs',json=payload)).json() for _ in range(2)]
                ids = [record['id'] for record in reversed(records)]
                saved = await client.post('/api/manual-inputs/playlists',json={'item_ids':ids,'name':'my folder'})
                self.assertEqual(saved.status_code,201,saved.text)
                self.assertEqual([item['id'] for item in saved.json()['items']],ids)
                self.assertEqual((await client.post('/api/manual-inputs/playlists',json={'item_ids':[ids[0],ids[0]]})).status_code,422)
                self.assertEqual((await client.post('/api/manual-inputs/playlists',json={'item_ids':[ids[0],'0'*32]})).status_code,404)
                self.assertEqual((await client.post('/api/manual-inputs/playlists',json={'item_ids':[]})).status_code,422)
                self.assertEqual(len((await client.get('/api/manual-inputs')).json()['items']),2)
            # A different application instance sees the same playlist and raw files.
            app2 = FastAPI(); app2.include_router(router)
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app2),base_url='http://test') as client:
                groups = (await client.get('/api/manual-inputs/playlists')).json()['items']
                self.assertEqual(len(groups),1)
                self.assertEqual(groups[0]['item_ids'],ids)
                self.assertEqual((await client.get(groups[0]['items'][0]['sensor_url'])).content,csv)
