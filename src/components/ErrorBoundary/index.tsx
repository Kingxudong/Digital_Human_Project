import React, { Component, ErrorInfo, ReactNode } from 'react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error?: Error;
}

class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // 完全静默处理错误，不显示任何错误信息
    // 只在开发环境下记录到控制台
    if (process.env.NODE_ENV === 'development') {
      console.log('ErrorBoundary caught an error (silent):', error.message);
    }
  }

  render() {
    if (this.state.hasError) {
      // 完全静默处理错误，不显示任何错误UI
      // 直接返回子组件，让应用继续运行
      return this.props.children;
    }

    return this.props.children;
  }
}

export default ErrorBoundary; 