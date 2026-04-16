declare module "react-plotly.js" {
  import * as React from "react";

  interface PlotlyProps extends React.HTMLAttributes<HTMLDivElement> {
    data?: any[];
    layout?: any;
    config?: any;
    frames?: any[];
    revision?: number;
    style?: React.CSSProperties;
    useResizeHandler?: boolean;
  }

  const Plot: React.ComponentType<PlotlyProps>;
  export default Plot;
}
