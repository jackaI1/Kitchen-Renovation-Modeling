import copy,json,unittest
from pathlib import Path
from source_validation import validate_source
SOURCE=json.loads((Path(__file__).resolve().parents[1]/'data/source/vessel.json').read_text())
class SourceTests(unittest.TestCase):
    def test_accepts_source(self): self.assertEqual(validate_source(SOURCE),4)
    def test_rejects_duplicate(self):
        data=copy.deepcopy(SOURCE);data['parts'][1]['id']=data['parts'][0]['id']
        with self.assertRaisesRegex(ValueError,'names'):validate_source(data)
    def test_rejects_missing(self):
        data=copy.deepcopy(SOURCE);data['parts'].pop()
        with self.assertRaisesRegex(ValueError,'names'):validate_source(data)
    def test_rejects_bad_dimension(self):
        data=copy.deepcopy(SOURCE);data['parts'][0]['size'][0]=-1
        with self.assertRaisesRegex(ValueError,'dimensions'):validate_source(data)
    def test_rejects_non_finite(self):
        data=copy.deepcopy(SOURCE);data['parts'][0]['center'][0]=float('nan')
        with self.assertRaisesRegex(ValueError,'finite'):validate_source(data)
    def test_rejects_units(self):
        data=copy.deepcopy(SOURCE);data['units']='feet'
        with self.assertRaisesRegex(ValueError,'metres'):validate_source(data)
    def test_rejects_station_order(self):
        data=copy.deepcopy(SOURCE);data['stations'].reverse()
        with self.assertRaisesRegex(ValueError,'stations'):validate_source(data)
if __name__=='__main__':unittest.main()
