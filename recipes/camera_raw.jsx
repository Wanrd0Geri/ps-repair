// 配方：camera_raw
// 用途：Camera Raw 滤镜：在副本上做去朦胧、纹理、清晰度、高光/阴影等 ACR 调整，蒙版只露选区。
// 参数（都可选，默认 0 = 不动；范围同 ACR 面板）：
//   doc_id       int      默认=当前文档
//   exposure     number   -5..5（档）
//   contrast / highlights / shadows / whites / blacks   int   -100..100
//   texture / clarity / dehaze / vibrance / saturation  int   -100..100
//   selection    选区     默认=沿用当前选区；无选区=整层（蒙版全显）
//   layer_id / source / expand_px / feather_px / label   同 content_aware_fill
// 产出：图层「修_camera_raw_<label>」= 源图层副本（ACR 处理后）+ 选区蒙版；结束后取消选区
// 验证：2026-09-25 PS 27.10.0 已验证（tests/run_tests.py；另测 exposure +1/-1：区内平均亮度 129→172 / 119→82，
//   区外不变）。实测过 exposure/dehaze/clarity；其余键名来自 Camera Raw.plugin 的 AETE 术语表
//   （Cr12/Hi12/Sh12/Wh12/Bk12/CrTx/Vibr/Strt），未逐个验证。
// 费用/限制：本地、不扣积分；ACR 按整层上下文算（去朦胧、清晰度看全局），所以在“选区外接框+余量”内计算
//   结果会和整图做略有不同；ACR 版本升级可能改键名。

var ACR_KEYS = { contrast: 'Cr12', highlights: 'Hi12', shadows: 'Sh12', whites: 'Wh12', blacks: 'Bk12',
                 texture: 'CrTx', clarity: 'Cl12', dehaze: 'Dhze', vibrance: 'Vibr', saturation: 'Strt' };

function run(args) {
  var doc = getDoc(args);
  var d = new ActionDescriptor(), used = {}, n = 0;
  d.putString(cTID('CMod'), 'Filter');
  d.putEnumerated(cTID('Sett'), cTID('Sett'), cTID('Cst '));
  d.putEnumerated(cTID('WBal'), cTID('WBal'), cTID('AsSh'));
  var ex = opt(args, 'exposure', null);
  if (ex !== null) { if (!(ex >= -5 && ex <= 5)) fail('BAD_ARG', 'exposure -5..5'); d.putDouble(cTID('Ex12'), Number(ex)); used.exposure = ex; n++; }
  for (var k in ACR_KEYS) {
    var v = opt(args, k, null);
    if (v === null) continue;
    if (!(v >= -100 && v <= 100)) fail('BAD_ARG', k + ' -100..100');
    d.putInteger(cTID(ACR_KEYS[k]), Math.round(Number(v)));
    used[k] = v; n++;
  }
  if (!n) fail('BAD_ARG', '至少给一个调整参数（如 dehaze:20）');
  var info = filterFlow(doc, args, 'camera_raw', 64, function () {
    executeAction(sTID('Adobe Camera Raw Filter'), d, DialogModes.NO);
  });
  info.acr = used;
  return info;
}
