// 配方：layer_ops
// 用途：图层小操作：rename / opacity / blend / visible / move / delete / select / info。
// 参数（单步写在顶层，多步用 ops 列表，每步字段相同）：
//   doc_id            int     默认=当前文档
//   op                str     rename|opacity|blend|visible|move|delete|select|info
//   layer_id          int     默认=当前图层
//   name              str     rename 用；没带“修_”前缀会自动补上（保持受保护可识别）
//   value             number/bool   opacity 用 0-100；visible 用 true/false
//   mode              str     blend 用：normal/multiply/screen/overlay/soft_light/color/luminosity 等
//   to                str     move 用：top|bottom|above|below（above/below 需要 ref_layer_id）
//   ref_layer_id      int     move 的参照图层
//   ops               list    多步，如 [{"op":"opacity","layer_id":5,"value":60},{"op":"move","layer_id":5,"to":"top"}]
//   allow_any_layer   bool    默认=false   除 select/info 外，默认只改名字以“修_”开头的图层
// 产出：改动后的图层信息列表（delete 返回被删图层的 id/名称）
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py 覆盖全部 op 与保护）
// 费用/限制：本地、不扣积分；delete 可用 PS 历史撤销，但脚本里视为不可逆，只删自己建的“修_”层。

function moveLayer(doc, layer, o) {
  var to = o.to;
  if (to == 'top') { if (doc.layers[0].id != layer.id) layer.move(doc.layers[0], ElementPlacement.PLACEBEFORE); }
  else if (to == 'bottom') {
    var last = doc.layers[doc.layers.length - 1];
    if (last.typename == 'ArtLayer' && last.isBackgroundLayer) layer.move(last, ElementPlacement.PLACEBEFORE);
    else if (last.id != layer.id) layer.move(last, ElementPlacement.PLACEAFTER);
  } else if (to == 'above' || to == 'below') {
    if (o.ref_layer_id === undefined || o.ref_layer_id === null) fail('BAD_ARG', 'move above/below 需要 ref_layer_id');
    var ref = findLayer(doc, o.ref_layer_id);
    layer.move(ref, to == 'above' ? ElementPlacement.PLACEBEFORE : ElementPlacement.PLACEAFTER);
  } else fail('BAD_ARG', 'move 的 to 只能是 top/bottom/above/below');
}

function doOp(doc, o, args) {
  var layer = sourceLayer(doc, o);
  var guard = { allow_any_layer: opt(o, 'allow_any_layer', opt(args, 'allow_any_layer', false)) };
  var op = o.op;
  if (op == 'select') { doc.activeLayer = layer; return layerInfo(layer); }
  if (op == 'info') return layerInfo(layer);
  assertOwnLayer(layer, guard);
  if (op == 'rename') {
    var n = String(opt(o, 'name', ''));
    if (!n) fail('BAD_ARG', 'rename 需要 name');
    layer.name = (n.indexOf(FIX_PREFIX) == 0) ? n : FIX_PREFIX + n;
  } else if (op == 'opacity') {
    var v = Number(o.value);
    if (!(v >= 0 && v <= 100)) fail('BAD_ARG', 'opacity value 0-100');
    layer.opacity = v;
  } else if (op == 'blend') {
    layer.blendMode = blendMode(o.mode);
  } else if (op == 'visible') {
    if (typeof o.value != 'boolean') fail('BAD_ARG', 'visible value 需要 true/false');
    layer.visible = o.value;
  } else if (op == 'move') {
    moveLayer(doc, layer, o);
  } else if (op == 'delete') {
    var gone = { id: layer.id, name: layer.name, deleted: true };
    layer.remove();
    return gone;
  } else fail('BAD_ARG', '未知 op：' + op);
  return layerInfo(layer);
}

function run(args) {
  var doc = getDoc(args);
  var ops = opt(args, 'ops', null) || [args];
  var out = [];
  for (var i = 0; i < ops.length; i++) out.push(doOp(doc, ops[i], args));
  return { results: out };
}
