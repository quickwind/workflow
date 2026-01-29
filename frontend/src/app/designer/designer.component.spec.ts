import { TestBed } from '@angular/core/testing';
import { PLATFORM_ID } from '@angular/core';

import { DesignerComponent } from './designer.component';
import { WorkflowsApiService } from '../core/workflows-api.service';

describe('DesignerComponent (smoke)', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [DesignerComponent],
      providers: [
        { provide: PLATFORM_ID, useValue: 'server' },
        { provide: WorkflowsApiService, useValue: {} },
      ],
    }).compileComponents();
  });

  it('creates in non-browser mode without initializing editors', () => {
    const fixture = TestBed.createComponent(DesignerComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    expect(component).toBeTruthy();
    expect(component.status).toContain('Browser-only');
  });
});
