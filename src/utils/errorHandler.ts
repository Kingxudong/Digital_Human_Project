// 全局错误处理工具
class GlobalErrorHandler {
  private static instance: GlobalErrorHandler;
  private errorCount = 0;
  private readonly maxErrors = 5; // 最大错误数量
  private readonly errorWindow = 10000; // 10秒内的错误窗口
  private lastErrorTime = 0;

  private constructor() {
    this.setupGlobalErrorHandlers();
  }

  static getInstance(): GlobalErrorHandler {
    if (!GlobalErrorHandler.instance) {
      GlobalErrorHandler.instance = new GlobalErrorHandler();
    }
    return GlobalErrorHandler.instance;
  }

  private setupGlobalErrorHandlers() {
    // 捕获未处理的JavaScript错误 - 完全静默处理
    window.addEventListener('error', (event) => {
      // 阻止默认错误显示
      event.preventDefault();
      this.handleError(event.error || new Error(event.message), 'JavaScript Error');
    });

    // 捕获未处理的Promise拒绝 - 完全静默处理
    window.addEventListener('unhandledrejection', (event) => {
      // 阻止默认错误显示
      event.preventDefault();
      this.handleError(new Error(event.reason), 'Unhandled Promise Rejection');
    });

    // 捕获控制台错误 - 完全静默处理
    const originalConsoleError = console.error;
    console.error = (...args) => {
      // 只在开发环境下记录原始错误，但不显示
      if (process.env.NODE_ENV === 'development') {
        originalConsoleError.apply(console, args);
      }
      
      // 检查是否是PeerConnection相关错误
      const errorMessage = args.join(' ');
      if (this.isPeerConnectionError(errorMessage)) {
        this.handleError(new Error(errorMessage), 'PeerConnection Error');
      }
    };

    // 捕获console.warn中的连接错误 - 完全静默处理
    const originalConsoleWarn = console.warn;
    console.warn = (...args) => {
      // 只在开发环境下记录原始警告，但不显示
      if (process.env.NODE_ENV === 'development') {
        originalConsoleWarn.apply(console, args);
      }
      
      const warningMessage = args.join(' ');
      if (this.isConnectionWarning(warningMessage)) {
        this.handleError(new Error(warningMessage), 'Connection Warning');
      }
    };

    // 禁用React错误边界的错误显示
    this.disableReactErrorBoundary();
  }

  private disableReactErrorBoundary() {
    // 覆盖React的错误边界显示
    const originalConsoleError = console.error;
    console.error = (...args) => {
      const message = args.join(' ');
      
      // 过滤掉React错误边界的错误显示
      if (message.includes('Uncaught runtime errors:') || 
          message.includes('The operation was aborted') ||
          message.includes('ErrorBoundary') ||
          message.includes('React Error Boundary')) {
        // 完全静默处理，不显示任何错误
        return;
      }
      
      // 其他错误只在开发环境下记录
      if (process.env.NODE_ENV === 'development') {
        originalConsoleError.apply(console, args);
      }
    };
  }

  private isPeerConnectionError(message: string): boolean {
    const peerConnectionErrors = [
      'connectionState',
      'PeerConnection',
      'Cannot read properties of undefined',
      'TypeError',
      'WebRTC',
      'RTC',
      'ICE',
      'DTLS',
      'SDP',
      'The operation was aborted',
      'Uncaught runtime errors'
    ];
    
    return peerConnectionErrors.some(error => 
      message.toLowerCase().includes(error.toLowerCase())
    );
  }

  private isConnectionWarning(message: string): boolean {
    const connectionWarnings = [
      'connection',
      'timeout',
      'failed',
      'error',
      'disconnected',
      'unavailable',
      'aborted',
      'operation'
    ];
    
    return connectionWarnings.some(warning => 
      message.toLowerCase().includes(warning.toLowerCase())
    );
  }

  private handleError(error: Error, type: string) {
    const now = Date.now();
    
    // 重置错误计数（如果超过时间窗口）
    if (now - this.lastErrorTime > this.errorWindow) {
      this.errorCount = 0;
    }
    
    this.errorCount++;
    this.lastErrorTime = now;

    // 只在开发环境下记录详细错误，但不显示
    if (process.env.NODE_ENV === 'development') {
      console.log(`[${type}] ${error.message}`, error.stack);
    }

    // 完全禁用错误提示显示
    // 不显示任何错误信息给用户
  }

  // 手动触发错误处理（用于特定场景）
  public triggerError(message: string, type: string = 'Manual Error') {
    this.handleError(new Error(message), type);
  }

  // 重置错误计数
  public resetErrorCount() {
    this.errorCount = 0;
    this.lastErrorTime = 0;
  }
}

// 导出单例实例
export const globalErrorHandler = GlobalErrorHandler.getInstance();

// 导出便捷方法
export const handleGlobalError = (error: Error, type?: string) => {
  globalErrorHandler.triggerError(error.message, type || 'Custom Error');
};

export const resetGlobalErrorCount = () => {
  globalErrorHandler.resetErrorCount();
}; 