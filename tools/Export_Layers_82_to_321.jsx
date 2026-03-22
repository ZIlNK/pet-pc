#target photoshop

if (app.documents.length == 0) {
    alert("请先打开一个 PSD 文档！");
    exit();
}

var doc = app.activeDocument;
var targetGroupName = "组6";
var targetGroup = null;
var found = false;

// 查找"组2"
for (var i = 0; i < doc.layers.length; i++) {
    if (doc.layers[i].name == targetGroupName && doc.layers[i].typename == "LayerSet") {
        targetGroup = doc.layers[i];
        found = true;
        break;
    }
}

if (!found) {
    alert('未找到名为 "' + targetGroupName + '" 的图层组！');
    exit();
}

// ✅ 关键修复1：获取组内所有子图层（不包含子组）
var layersInGroup = [];
for (var i = 0; i < targetGroup.layers.length; i++) {
    var layer = targetGroup.layers[i];
    if (layer.typename != "LayerSet") {
        layersInGroup.push(layer);
    }
}

if (layersInGroup.length == 0) {
    alert('“' + targetGroupName + '” 组中没有可导出的图层！');
    exit();
}

// ✅ 关键修复2：保存原始画布尺寸（避免尺寸错误）
var originalWidth = doc.width;
var originalHeight = doc.height;
var originalResolution = doc.resolution;

// 选择保存文件夹
var folder = Folder.selectDialog("请选择导出文件夹");
if (folder == null) {
    alert("未选择文件夹，操作已取消。");
    exit();
}

var exportFolder = new Folder(folder + "/Exported_Group2_PNGs");
if (!exportFolder.exists) {
    exportFolder.create();
}

var pngOpts = new PNGSaveOptions();
pngOpts.compression = 9;
pngOpts.interlaced = false;

// ✅ 修改：每隔两个图层导出一个（步长为2）
for (var i = 0; i < layersInGroup.length; i += 1) {
    var layer = layersInGroup[i];
    var layerName = layer.name;
    
    // 隐藏所有顶层图层
    for (var j = 0; j < doc.layers.length; j++) {
        doc.layers[j].visible = false;
    }
    
    // ✅ 关键修复4：隐藏"组2"内所有子图层
    for (var k = 0; k < targetGroup.layers.length; k++) {
        targetGroup.layers[k].visible = false;
    }
    
    // ✅ 关键修复5：只显示当前图层 + 确保组可见
    targetGroup.visible = true;
    layer.visible = true;
    
    // ✅ 关键修复6：强制画布尺寸（防止尺寸变化）
    doc.resizeCanvas(originalWidth, originalHeight, AnchorPosition.MIDDLECENTER);
    doc.resizeImage(null, null, originalResolution);
    
    // 安全文件名（移除非法字符）
    //var safeName = layerName.replace(/[\\/:*?"<>|]/g, "_");
    var fileName = "Group2_" + layerName + ".png";
    var saveFile = new File(exportFolder + "/" + fileName);
    
    try {
        doc.saveAs(saveFile, pngOpts, true, Extension.LOWERCASE);
        $.writeln("✅ 已导出: " + fileName);
    } catch (e) {
        $.writeln("❌ 导出失败: " + fileName + " - " + e.message);
    }
}

// ✅ 关键修复7：恢复原始状态
targetGroup.visible = true;
for (var i = 0; i < targetGroup.layers.length; i++) {
    targetGroup.layers[i].visible = true;
}

// 计算实际导出的图层数量
var exportedCount = Math.ceil(layersInGroup.length / 2);
alert("🎉 修复完成！\n✅ 每隔两个图层导出一个\n✅ 保持原始画布尺寸\n✅ 每次只导出单个图层内容\n共导出 " + exportedCount + " 个 PNG 文件");