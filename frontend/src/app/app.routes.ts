import { Routes } from '@angular/router';

import { DesignerComponent } from './designer/designer.component';
import { InstancesComponent } from './instances/instances.component';
import { InstanceViewerComponent } from './instances/instance-viewer.component';

export const appRoutes: Routes = [
  { path: '', redirectTo: 'designer', pathMatch: 'full' },
  { path: 'designer', component: DesignerComponent },
  { path: 'instances', component: InstancesComponent },
  { path: 'instances/:instanceId', component: InstanceViewerComponent },
  { path: '**', redirectTo: 'designer' }
];
