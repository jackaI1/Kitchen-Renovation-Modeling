"""blender --background --factory-startup --python-exit-code 1 --python pipeline/export_vessel.py
Optional: -- --source path/to/source.json --output path/to/vessel.glb
"""
import argparse,json,sys
from pathlib import Path
import bpy,bmesh
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'pipeline'))
from source_validation import validate_source
parser=argparse.ArgumentParser()
parser.add_argument('--source',type=Path,default=ROOT/'data/source/vessel.json')
parser.add_argument('--output',type=Path,default=ROOT/'public/models/vessel.glb')
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
data=json.loads(args.source.read_text());validate_source(data)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
bpy.context.scene.unit_settings.system='METRIC'
# Each station is a keel/side cross-section; omit the deck for a useful cutaway.
vertices=[]
for x,w in data['stations']:vertices.extend([(x,-w,2),(x,-w*.68,0),(x,w*.68,0),(x,w,2)])
faces=[]
for i in range(len(data['stations'])-1):
    for j in range(3):a=i*4+j;faces.append((a,a+4,a+5,a+1))
faces.extend([(3,2,1,0),tuple(range(len(vertices)-4,len(vertices)))])
mesh=bpy.data.meshes.new('hull_geometry');mesh.from_pydata(vertices,[],faces);mesh.update()
hull=bpy.data.objects.new('hull',mesh);bpy.context.collection.objects.link(hull)
for part in data['parts']:
    bpy.ops.mesh.primitive_cube_add(size=1,location=part['center']);obj=bpy.context.object
    obj.name=part['id'];obj.dimensions=part['size'];obj['label']=part['label']
# Bake units/transforms, weld coincident vertices, remove loose data, triangulate.
# Keep parts separate: their names are the telemetry contract.
report={'source':str(args.source.name),'units':'metres','parts':[]}
for obj in list(bpy.context.scene.objects):
    if obj.type!='MESH':continue
    bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
    bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
    before=len(obj.data.vertices);bm=bmesh.new();bm.from_mesh(obj.data)
    bmesh.ops.remove_doubles(bm,verts=list(bm.verts),dist=0.0001)
    loose=[v for v in bm.verts if not v.link_faces]
    if loose:bmesh.ops.delete(bm,geom=loose,context='VERTS')
    bmesh.ops.recalc_face_normals(bm,faces=list(bm.faces));bmesh.ops.triangulate(bm,faces=list(bm.faces))
    bm.to_mesh(obj.data);bm.free();obj.data.update()
    material=bpy.data.materials.new(obj.name+'_material');material.diffuse_color=(0.35,0.52,0.61,1)
    obj.data.materials.clear();obj.data.materials.append(material)
    report['parts'].append({'name':obj.name,'vertices_before':before,'vertices_after':len(obj.data.vertices),'triangles':len(obj.data.polygons)})
args.output.parent.mkdir(parents=True,exist_ok=True)
bpy.ops.export_scene.gltf(filepath=str(args.output),export_format='GLB',export_yup=True,export_apply=True,export_extras=True,export_animations=False,export_cameras=False,export_lights=False)
report['bytes']=args.output.stat().st_size
args.output.with_suffix('.report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
