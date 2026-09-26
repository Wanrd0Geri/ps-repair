// 配方：generative_fill
// 用途：PS 生成式填充（Firefly，云端）：小块去物件、补小面积纹理。大结构（屋檐、窗格、招牌）不要用——
//   实测会凭空长出金属结构，大问题回即梦局部重绘。
// 参数：
//   doc_id      int      默认=当前文档
//   selection   选区     默认="current"   必须有选区；越小越好
//   prompt      str      默认=""          空提示词 = 按周围内容补（去物件优先用空）
//   expand_px   int      默认=0           生成前把选区外扩（PS 自己还会再外扩约 11 px）
//   layer_id    int      默认=背景层（没有背景层时用当前图层）   复制成「修_genfill_src」作为生成目标
//   source      str      默认="layer"     "merged"=盖印可见图层作为「修_genfill_src」
//   keep_src_visible  bool  默认=false    生成后「修_genfill_src」是否保持可见（它和源图层像素相同）
//   label       str      默认=""
//   dry_run     bool     默认=false       true=只校验参数、拼描述符并返回，不复制图层、不调用云端、不扣积分
//   to_top      bool     默认=true        生成后把产出层移到最顶层（false=留在源图层正上方，会被上面的修复层盖住）
// 产出：「修_genfill_src」（源图层普通副本，默认隐藏）+ 「修_generative_fill_<label>」（PS 产出的带蒙版智能对象层）
// 验证：2026-09-25 PS 27.10.0 实跑通过（ps-repair e2e，3488×1480 实图，直接在工作文档上跑）：复制背景层为
//   「修_genfill_src」再生成，106 秒，产出带用户蒙版的智能对象层，bounds 比选区四边各外扩 11 px，背景层不动。
//   描述符来自 genfill_test2.jsx（plain 变体，不带 serviceOptionsList，229 秒）。dry_run 已验证；tests 不跑它。
// 费用/限制：**每次扣 Adobe 生成积分**，需要联网登录；1.5–4 分钟，可能超过 2 分钟（psrun 会在 AppleEvent 超时 -1712 后
//   轮询结果文件，调用时给 --timeout 900）；「修_genfill_src」插在源图层正上方（隐藏），产出层默认移到最顶层（to_top=true；移层逻辑同 layer_ops move，未单独实跑）；
//   每次结果不同，再跑一次就再扣一次积分。

function run(args) {
  var doc = getDoc(args);
  var prompt = String(opt(args, 'prompt', ''));
  var label = opt(args, 'label', '');
  applySelection(doc, opt(args, 'selection', 'current'));
  if (!hasSelection(doc)) fail('NO_SELECTION', '生成式填充需要选区');
  expandSelection(doc, opt(args, 'expand_px', 0));
  var selB = selBounds(doc);
  var src = null;
  if (opt(args, 'source', 'layer') != 'merged') {
    if (args.layer_id !== undefined && args.layer_id !== null) src = findLayer(doc, args.layer_id);
    else { try { src = doc.backgroundLayer; } catch (e) { src = doc.activeLayer; } }
    if (src.typename != 'ArtLayer' || src.kind != LayerKind.NORMAL) fail('SOURCE_NOT_PIXEL_LAYER', '源图层不是普通像素层；可传 source:"merged"');
  }
  if (opt(args, 'dry_run', false)) {
    return { dry_run: true, selection: selB, prompt: prompt, source_layer_id: src ? src.id : 'merged',
             descriptor: { event: 'syntheticFill', serviceID: 'clio', workflowType: 'genWorkflow.in_painting',
                           documentID: doc.id, layerID: '<修_genfill_src 的 id>' } };
  }
  var work;
  if (src) { doc.activeLayer = src; work = src.duplicate(); } else work = stampVisible(doc);
  work.name = FIX_PREFIX + 'genfill_src';
  doc.activeLayer = work;
  var t0 = new Date().getTime();
  var d = new ActionDescriptor(); var r = new ActionReference();
  r.putEnumerated(sTID('document'), sTID('ordinal'), sTID('targetEnum'));
  d.putReference(sTID('null'), r);
  d.putInteger(sTID('documentID'), doc.id);
  d.putInteger(sTID('layerID'), work.id);
  d.putString(sTID('prompt'), prompt);
  d.putString(sTID('serviceID'), 'clio');
  d.putEnumerated(sTID('workflowType'), sTID('genWorkflow'), sTID('in_painting'));
  try {
    executeAction(sTID('syntheticFill'), d, DialogModes.NO);
  } catch (e) {
    discardLayer(work);  // 失败不留「修_genfill_src」
    throw e;
  }
  var gen = doc.activeLayer;
  if (gen.id == work.id) { discardLayer(work); fail('NO_RESULT', '生成式填充没有产出新图层'); }
  gen.name = fixName('generative_fill', label);
  work.visible = !!opt(args, 'keep_src_visible', false);
  // PS 把产出层插在源图层正上方，会被上面已有的修复层盖住；默认移到最顶层（逻辑同 layer_ops move top）
  if (opt(args, 'to_top', true) && doc.layers[0].id != gen.id) gen.move(doc.layers[0], ElementPlacement.PLACEBEFORE);
  doc.selection.deselect();
  doc.activeLayer = gen;
  var info = layerInfo(gen);
  info.src_layer_id = work.id;
  info.selection = selB;
  info.cloud_ms = new Date().getTime() - t0;
  return info;
}
