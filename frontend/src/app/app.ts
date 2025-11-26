// src/app/app.ts
import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet],
  template: '<router-outlet></router-outlet>',
  styleUrls: ['./app.scss'],
})
export class AppComponent {
  title = 'jsapi-angular';
}
