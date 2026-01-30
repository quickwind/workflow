# bpmn-instance-viewer-js

Reusable, framework-agnostic BPMN instance viewer built on `bpmn-js` Viewer.

## Usage

```ts
import { render, type InstanceState } from './src/index';

const state: InstanceState = {
  tasks: [
    {
      elementId: 'UserTask_1',
      status: 'completed',
      started_at: '2026-01-30T09:55:00Z',
      completed_at: '2026-01-30T10:00:00Z',
      user: { id: 'user123', name: 'John Doe' },
      input_data: {},
      output_data: { field: 'value' }
    }
  ],
  sequenceFlows: [{ elementId: 'Flow_1', status: 'traversed' }]
};

await render(containerElement, bpmnXml, state);
```
