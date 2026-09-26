// 配方：select_sky
// 用途：PS“选择 > 天空”，自动选出天空区域（替换当前选区）。
// 参数：
//   doc_id   int   默认=当前文档
// 产出：选区；返回 bounds，没识别到天空时 found=false、bounds=null
// 验证：2026-09-25 PS 27.10.0 已验证（真实夜景图 bounds 0,0,3486,356；合成测试图见 tests/run_tests.py）
// 费用/限制：本机模型运算、不扣积分；作用于合成画面；识别结果常带软边，出错多在树梢/屋檐交界，用前先 zoom 看边缘。

function run(args) {
  var doc = getDoc(args);
  doc.selection.deselect();
  executeAction(sTID('selectSky'), undefined, DialogModes.NO);
  var b = selBounds(doc);
  return { found: b !== null, bounds: b };
}
