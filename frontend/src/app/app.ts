import { Component } from '@angular/core';
import { DesignerComponent } from './designer/designer.component';

@Component({
  selector: 'app-root',
  imports: [DesignerComponent],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App {
}
