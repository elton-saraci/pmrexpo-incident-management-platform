import { Component } from '@angular/core';
import { FormControl, FormGroup } from '@angular/forms';

// User UI
// - Send Coordinates
// - Open Camera
// 	- jpg
// - Description
// - Type
// 	- Dropdown

@Component({
  selector: 'app-user-component',
  imports: [],
  templateUrl: './user-component.html',
  styleUrl: './user-component.scss',
})
export class UserComponent {
  form = new FormGroup({
    type: new FormControl(""),
    description: new FormControl(""),
    coordinates: new FormControl(""),
    attachments: new FormControl("")
  });
}
