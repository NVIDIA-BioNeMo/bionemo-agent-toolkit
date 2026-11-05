"""Actual local export bytes and integrity; no model, registry or GPU required."""
import base64,json,sys,tempfile,unittest,zipfile,io
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'integrations/atomworks-studio/scripts'))
from local_exports import save,get

class LocalExportTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
 def test_cif_saved_exactly_and_immutable_across_later_exports(self):
  first=save(self.root,'protein binder.cif','chemical/x-mmcif',text='data_科学\n')
  second=save(self.root,'protein binder.cif','chemical/x-mmcif',text='data_changed\n')
  a=get(self.root,first['export_id']);b=get(self.root,second['export_id'])
  self.assertNotEqual(a['path'],b['path']);self.assertEqual(Path(a['path']).read_text(),'data_科学\n')
  self.assertEqual(Path(a['path']).stat().st_mode&0o777,0o600)
 def test_actual_zip_round_trip(self):
  buf=io.BytesIO()
  with zipfile.ZipFile(buf,'w') as z:z.writestr('design/input.cif','data_test\n')
  saved=save(self.root,'results.zip','application/zip',base64_data=base64.b64encode(buf.getvalue()).decode())
  with zipfile.ZipFile(get(self.root,saved['export_id'])['path']) as z:self.assertEqual(z.read('design/input.cif'),b'data_test\n')
 def test_changed_file_or_receipt_is_rejected(self):
  saved=save(self.root,'input.cif','chemical/x-mmcif',text='data_original')
  path=Path(get(self.root,saved['export_id'])['path']);path.write_text('changed')
  with self.assertRaisesRegex(ValueError,'changed'):get(self.root,saved['export_id'])
  receipt=path.parent/'receipt.json';record=json.loads(receipt.read_text());record['filename']='../../elsewhere';receipt.write_text(json.dumps(record))
  with self.assertRaises(ValueError):get(self.root,saved['export_id'])
 def test_invalid_payloads_and_paths_do_not_escape_export_directory(self):
  for args in [('a.txt','text/plain','x',None),('a.cif','chemical/x-mmcif','x','eA=='),('a.zip','application/zip',None,'!!!')]:
   with self.assertRaises(ValueError):save(self.root,*args)
  for value in ('../x','A'*32,'f'*31):
   with self.assertRaises(ValueError):get(self.root,value)
  saved=save(self.root,'../../a.cif','chemical/x-mmcif',text='data_x')
  self.assertTrue(Path(get(self.root,saved['export_id'])['path']).is_relative_to(self.root.resolve()/'exports'))
 def test_symlink_and_oversize_exports_refused(self):
  (self.root/'exports').symlink_to(self.root,target_is_directory=True)
  with self.assertRaises(ValueError):save(self.root,'a.cif','chemical/x-mmcif',text='data_x')
  (self.root/'exports').unlink()
  from unittest.mock import patch
  with patch('local_exports.LIMIT',4):
   with self.assertRaises(ValueError):save(self.root,'a.cif','chemical/x-mmcif',text='12345')
