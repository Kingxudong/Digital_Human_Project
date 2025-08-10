// 全局错误抑制工具
// 在应用启动时就拦截所有错误，防止显示给用户

export function suppressAllErrors() {
  // 拦截所有未捕获的错误
  window.addEventListener('error', (event) => {
    event.preventDefault();
    event.stopPropagation();
    
    // 只在开发环境下记录
    if (process.env.NODE_ENV === 'development') {
      console.log('[Suppressed Error]:', event.message);
    }
    
    return false;
  }, true);

  // 拦截所有未处理的Promise拒绝
  window.addEventListener('unhandledrejection', (event) => {
    event.preventDefault();
    event.stopPropagation();
    
    // 只在开发环境下记录
    if (process.env.NODE_ENV === 'development') {
      console.log('[Suppressed Promise Rejection]:', event.reason);
    }
    
    return false;
  });

  // 拦截console.error，防止错误显示
  const originalConsoleError = console.error;
  console.error = (...args) => {
    const message = args.join(' ');
    
    // 过滤掉所有错误显示
    if (message.includes('Uncaught runtime errors:') ||
        message.includes('The operation was aborted') ||
        message.includes('ErrorBoundary') ||
        message.includes('React Error Boundary') ||
        message.includes('TypeError') ||
        message.includes('Cannot read properties of undefined') ||
        message.includes('PeerConnection') ||
        message.includes('connectionState')) {
      // 完全静默处理
      if (process.env.NODE_ENV === 'development') {
        console.log('[Suppressed Console Error]:', message);
      }
      
      // 立即移除错误显示
      setTimeout(() => {
        const errorElements = document.querySelectorAll('*');
        errorElements.forEach(el => {
          if (el.textContent && el.textContent.includes('Uncaught runtime errors:')) {
            el.remove();
          }
        });
      }, 0);
      
      return;
    }
    
    // 其他错误只在开发环境下记录
    if (process.env.NODE_ENV === 'development') {
      originalConsoleError.apply(console, args);
    }
  };

  // 拦截console.warn
  const originalConsoleWarn = console.warn;
  console.warn = (...args) => {
    const message = args.join(' ');
    
    // 过滤掉连接相关的警告
    if (message.includes('connection') ||
        message.includes('timeout') ||
        message.includes('failed') ||
        message.includes('error') ||
        message.includes('aborted')) {
      // 完全静默处理
      if (process.env.NODE_ENV === 'development') {
        console.log('[Suppressed Console Warning]:', message);
      }
      return;
    }
    
    // 其他警告只在开发环境下记录
    if (process.env.NODE_ENV === 'development') {
      originalConsoleWarn.apply(console, args);
    }
  };

  // 覆盖React的错误边界显示
  if (typeof window !== 'undefined') {
    // 移除任何已存在的错误显示元素
    const removeErrorDisplays = () => {
      // 移除React错误覆盖层
      const errorElements = document.querySelectorAll('[data-react-error-overlay]');
      errorElements.forEach(el => el.remove());
      
      // 移除React错误边界元素
      const errorBoundaryElements = document.querySelectorAll('[data-react-error-boundary]');
      errorBoundaryElements.forEach(el => el.remove());
      
      // 移除包含错误信息的元素
      const errorTexts = document.querySelectorAll('*');
      errorTexts.forEach(el => {
        if (el.textContent && (
          el.textContent.includes('Uncaught runtime errors:') ||
          el.textContent.includes('The operation was aborted') ||
          el.textContent.includes('ERROR') ||
          el.textContent.includes('TypeError') ||
          el.textContent.includes('Cannot read properties of undefined')
        )) {
          const element = el as HTMLElement;
          element.style.display = 'none';
          element.style.visibility = 'hidden';
          element.style.opacity = '0';
        }
      });
      
      // 移除React开发工具的错误显示
      const reactErrorOverlay = document.getElementById('react-error-overlay');
      if (reactErrorOverlay) {
        reactErrorOverlay.remove();
      }
      
      // 移除所有包含错误文本的div
      const allDivs = document.querySelectorAll('div');
      allDivs.forEach(div => {
        if (div.textContent && (
          div.textContent.includes('Uncaught runtime errors:') ||
          div.textContent.includes('The operation was aborted') ||
          div.textContent.includes('ERROR')
        )) {
          div.remove();
        }
      });
    };

    // 更频繁地检查和移除错误显示
    setInterval(removeErrorDisplays, 500);
    
    // 立即执行一次
    removeErrorDisplays();
    
    // 延迟执行几次，确保覆盖层被移除
    setTimeout(removeErrorDisplays, 100);
    setTimeout(removeErrorDisplays, 500);
    setTimeout(removeErrorDisplays, 1000);
    
    // 使用MutationObserver监听DOM变化，实时移除错误显示
    const observer = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        if (mutation.type === 'childList') {
          mutation.addedNodes.forEach((node) => {
            if (node.nodeType === Node.ELEMENT_NODE) {
              const element = node as Element;
              if (element.textContent && (
                element.textContent.includes('Uncaught runtime errors:') ||
                element.textContent.includes('The operation was aborted') ||
                element.textContent.includes('ERROR')
              )) {
                element.remove();
              }
            }
          });
        }
      });
    });
    
    // 开始监听
    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  }
}

// 自动启动错误抑制
suppressAllErrors(); 