// 配方：select_subject
// 用途：PS“选择 > 主体”，自动选出画面主体（人物、建筑、物件），替换当前选区。
// 参数：
//   doc_id              int    默认=当前文档
//   sample_all_layers   bool   默认=false   true=按全部可见图层识别；false=只看当前图层
//   processing          str    默认="device"   device=本机处理；cloud=云端（更细，但要上传图片，未验证）
//   layer_id            int    默认=底层（通常是原图/背景）   sample_all_layers=false 时识别哪个图层
// 产出：选区；返回 bounds，没识别到主体时 found=false
// 验证：2026-09-25 PS 27.10.0 已验证（device；合成图选中红方块+黄圆 bounds 140,300,640,480）。
//   写法要点：autoCutout 必须带 null=文档引用（imageReference），否则报“没有这种元素”；再加
//   choice override imageProcessingSelectSubjectPrefs=imageProcessingModeDevice 固定本机处理。
//   上一轮失败写法：只带 sampleAllLayers 报“参数无效”，不带描述符报“没有这种元素”。
// 费用/限制：device 本地、不扣积分；cloud 未验证。AI 夜景里“主体”常被判成近景房屋或人物，范围先 zoom 核对。

function run(args) {
  var doc = getDoc(args);
  var proc = { device: 'imageProcessingModeDevice', cloud: 'imageProcessingModeCloud' }[opt(args, 'processing', 'device')];
  if (!proc) fail('BAD_ARG', 'processing 只能是 device/cloud');
  doc.activeLayer = (args.layer_id !== undefined && args.layer_id !== null) ? findLayer(doc, args.layer_id) : doc.layers[doc.layers.length - 1];
  doc.selection.deselect();
  var d = new ActionDescriptor(); var r = new ActionReference();
  r.putEnumerated(sTID('document'), sTID('ordinal'), sTID('targetEnum'));
  d.putReference(sTID('null'), r);
  d.putBoolean(sTID('sampleAllLayers'), !!opt(args, 'sample_all_layers', false));
  d.putEnumerated(sTID('imageProcessingSelectSubjectPrefs'), sTID('imageProcessingSelectSubjectPrefs'), sTID(proc));
  executeAction(sTID('autoCutout'), d, DialogModes.NO);
  var b = selBounds(doc);
  return { found: b !== null, bounds: b, processing: opt(args, 'processing', 'device') };
}
