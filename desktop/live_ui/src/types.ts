/** Wire types at the TypeScript/Tk compatibility boundary. */

declare global {
  var pywebview: {
    api: {
      snapshot(): Promise<State>;
      event(data: Info): Promise<void>;
      file_dialog(id: string): Promise<void>;
    };
  };
}

export type Info = Record<string, any>;

export interface ViewNode extends Info {
  id: string;
  kind: string;
  x: number;
  y: number;
  width: number;
  height: number;
  children: ViewNode[];
  style: Info;
}

export interface State {
  windows: ViewNode[];
  assets: Record<string, string>;
  menu?: Info;
  dialog?: Info;
  errors: string[];
  closed?: boolean;
}
