import { HttpClient } from '@angular/common/http';
import { Component, DOCUMENT, inject } from '@angular/core';
import { ReactiveFormsModule, FormsModule, FormControl, FormGroup, Validators } from '@angular/forms';
import { catchError, first, of } from 'rxjs';

// User UI
// - Send Coordinates
// - Open Camera
// 	- jpg
// - Description
// - Type
// 	- Dropdown

@Component({
  selector: 'app-user-component',
  imports: [FormsModule, ReactiveFormsModule],
  templateUrl: './user-component.html',
  styleUrl: './user-component.scss',
})
export class UserComponent {
  private readonly document = inject(DOCUMENT);
  private readonly window = this.document?.defaultView;

  private readonly httpClient = inject(HttpClient);

  private latitude: number;
  private longitude: number;

  form = new FormGroup({
    type: new FormControl("", Validators.required),
    description: new FormControl(""),
    attachments: new FormControl(null)
  });

  public async getCoordinates() {
    console.log("getCoordinates clicked");
    if (this.window) {
      console.log("window vorhanden");
      this.window.navigator.geolocation.getCurrentPosition(this.successGeolocation);
    }
  }

  public getLongAndLat() {
    return new Promise((resolve, reject) =>
        navigator.geolocation.getCurrentPosition(resolve, reject)
    );
}

  private successGeolocation(currentPosition: GeolocationPosition) {
    console.log("wann wird das hier aufgerufen");
    console.log(currentPosition.coords);
    console.log(currentPosition.coords.latitude);
    this.latitude = currentPosition.coords.latitude;
    this.longitude = currentPosition.coords.longitude;
  }

  public async formSubmit() {
    console.log("formSubmitted");
    await this.getLongAndLat().then((result: GeolocationPosition) => {
      this.longitude = result.coords.longitude;
      this.latitude = result.coords.latitude;
    });

    console.log(this.latitude);
    console.log(this.longitude);

    let url = "http://localhost:5000/api/incidents/report";

    this.httpClient.get(url).pipe(first()).subscribe(response => {
      console.log(response);
    });

    console.log("going to post");

    // let payload = {
    //   type: this.form.controls.type.value,
    //   latitude: this.latitude,
    //   longitude: this.longitude,
    //   description: this.form.controls.description.value
    // }

    // if (this.form.controls.attachments.value) {
    //   payload["files"] = [this.form.controls.attachments.value]
    // }

    const formData = new FormData();
    // Append form fields as strings
    formData.append("type", this.form.controls.type.value as string);
    formData.append("latitude", this.latitude.toString());
    formData.append("longitude", this.longitude.toString());
    // Optional fields
    if (this.form.controls.description.value) {
      formData.append("description", this.form.controls.description.value);
    }
    // Attachments (assuming the 'attachments' control holds a File object or similar)
    // NOTE: This assumes 'attachments' is correctly bound to a file input change event
    // that stores the actual File object, not just a string path.
    const file: File = (<HTMLInputElement>document.getElementById("attachmentControl")).files[0];
    console.log(file);
    if (file instanceof File) {
      console.log("appending file");
      // The second argument 'file.name' is optional but good practice
      formData.append("files", file, file.name);
    }

    console.log(formData);

    this.httpClient.post(url, formData).pipe(catchError(error => of(error))).subscribe(result => {console.log(result)});

    this.httpClient.get(url).pipe(first()).subscribe(response => {
      console.log(response);
    });
  }
}
