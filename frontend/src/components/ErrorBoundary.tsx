import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  message: string;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false, message: "" };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, message: error.message };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("[ErrorBoundary]", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-screen gap-4 p-8 text-center">
          <p className="text-xl font-semibold text-slate-800">Something went wrong</p>
          <p className="text-sm text-slate-500 max-w-md">{this.state.message}</p>
          <button
            onClick={() => window.location.reload()}
            className="px-4 py-2 text-sm rounded-md bg-brand-600 text-white hover:bg-brand-700"
          >
            Reload page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
