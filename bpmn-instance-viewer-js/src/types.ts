export type TaskStatus = 'completed' | 'in_progress' | 'waiting' | 'failed' | 'not_started';

export type SequenceFlowStatus = 'traversed' | 'not_started';

export type TaskUser = {
  id: string;
  name?: string;
} | null;

export type InstanceTaskState = {
  elementId: string;
  status: TaskStatus;
  started_at?: string | null;
  completed_at?: string | null;
  user?: TaskUser;
  input_data?: Record<string, unknown> | null;
  output_data?: Record<string, unknown> | null;
};

export type InstanceSequenceFlowState = {
  elementId: string;
  status: SequenceFlowStatus;
};

export type InstanceState = {
  tasks: InstanceTaskState[];
  sequenceFlows: InstanceSequenceFlowState[];
};

export type RenderResult = {
  viewer: unknown;
  destroy: () => Promise<void> | void;
};

export type RenderOptions = {
  fitViewport?: boolean;
};
