// 等待页面加载完成
document.addEventListener('DOMContentLoaded', function() {
  // 为搜索按钮添加点击事件
  var searchForm = document.getElementById('changelist-search');
  if (searchForm) {
    searchForm.addEventListener('submit', function(e) {
      // 阻止默认提交行为
      e.preventDefault();
      
      // 获取高级搜索按钮并点击它
      var advancedButton = document.querySelector('.search-advanced-toggle');
      if (advancedButton) {
        advancedButton.click();
      }
    });
  }
  
  // 为按钮添加title属性（原生浏览器提示）
  function addTooltip(selector, title) {
    var element = document.querySelector(selector);
    if (element) {
      element.setAttribute('title', title);
    }
  }
  
  // 为搜索框和按钮添加提示
  addTooltip('#searchbar', '输入关键字搜索');
  addTooltip('#changelist-search [type="submit"]', '点击搜索');
  
  // 为右上角的按钮添加提示
  var buttons = document.querySelectorAll('#changelist-form .actions .o-actions-list button');
  if (buttons.length >= 3) {
    buttons[0].setAttribute('title', '搜索用户');
    buttons[1].setAttribute('title', '刷新用户列表');
    buttons[2].setAttribute('title', '过滤选项');
  }
}); 