import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { Component, DOCUMENT, OnInit, inject } from '@angular/core';
import {
  ReactiveFormsModule,
  FormsModule,
  FormControl,
  FormGroup,
  Validators,
} from '@angular/forms';
import { NgIf } from '@angular/common';

@Component({
  selector: 'app-user-component',
  standalone: true,
  imports: [FormsModule, ReactiveFormsModule, NgIf],
  templateUrl: './user-component.html',
  styleUrls: ['./user-component.scss'],
})
export class UserComponent implements OnInit {
  private readonly document = inject(DOCUMENT);
  private readonly window = this.document?.defaultView;
  private readonly httpClient = inject(HttpClient);

  latitude: number | null = null;
  longitude: number | null = null;

  isGettingLocation = false;
  isRequestingCamera = false;
  cameraReady = false;
  cameraError = '';

  isSubmitting = false;
  submitSuccess = false;
  submitError = '';
  successMessage = 'Thank you. Your incident has been submitted.';

  locationError = '';
  selectedFileName = '';

  form = new FormGroup({
    type: new FormControl('', Validators.required),
    description: new FormControl(''),
    attachments: new FormControl<File | null>(null),
  });

  ngOnInit(): void {
    // Ask for location and camera as soon as the page loads
    this.autoGetLocation();
    this.requestCameraAccess();
  }

  // --- Location handling ---

  private async autoGetLocation() {
    this.locationError = '';
    this.isGettingLocation = true;

    try {
      const position = await this.getLongAndLat();
      this.latitude = position.coords.latitude;
      this.longitude = position.coords.longitude;
    } catch (err) {
      console.error(err);
      this.locationError =
        'We could not access your location automatically. Please allow location access in your browser settings if possible.';
    } finally {
      this.isGettingLocation = false;
    }
  }

  // Optional manual refresh button
  async onUseMyLocation() {
    await this.autoGetLocation();
  }

  public getLongAndLat(): Promise<GeolocationPosition> {
    return new Promise((resolve, reject) =>
      navigator.geolocation.getCurrentPosition(resolve, reject)
    );
  }

  // --- Camera permission ---

  private async requestCameraAccess() {
    this.cameraError = '';

    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      this.cameraError = 'Camera is not supported on this device.';
      return;
    }

    this.isRequestingCamera = true;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment' },
      });

      // We only need permission, stop stream immediately
      stream.getTracks().forEach((t) => t.stop());
      this.cameraReady = true;
    } catch (err) {
      console.error(err);
      this.cameraError =
        'Camera access was denied. You can still upload a photo from your gallery.';
      this.cameraReady = false;
    } finally {
      this.isRequestingCamera = false;
    }
  }

  // --- File selection ---

  onFileSelected(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) {
      this.form.controls.attachments.setValue(file);
      this.selectedFileName = file.name;
    } else {
      this.form.controls.attachments.setValue(null);
      this.selectedFileName = '';
    }
  }

  // --- Submit ---

  public async formSubmit() {
    if (this.form.invalid) return;

    this.isSubmitting = true;
    this.submitSuccess = false;
    this.submitError = '';
    this.locationError = '';

    // Make sure we have coordinates; try again if needed
    if (!this.latitude || !this.longitude) {
      try {
        const position = await this.getLongAndLat();
        this.latitude = position.coords.latitude;
        this.longitude = position.coords.longitude;
      } catch (err) {
        console.error(err);
        this.locationError =
          'Could not access your location. Please allow location access and try again.';
        this.isSubmitting = false;
        return;
      }
    }

    const url = 'http://localhost:8080/api/incidents/report';

    const formData = new FormData();
    formData.append('type', this.form.controls.type.value as string);
    formData.append('latitude', this.latitude.toString());
    formData.append('longitude', this.longitude.toString());

    const desc = this.form.controls.description.value;
    if (desc) {
      formData.append('description', desc);
    }

    const file = this.form.controls.attachments.value;
    if (file instanceof File) {
      formData.append('files', file, file.name);
    }

    this.httpClient
      .post(url, formData, { observe: 'response' })
      .subscribe({
        next: (response) => {
          if (response.status === 201) {
            this.submitSuccess = true;
            this.submitError = '';
            this.form.reset();
            this.selectedFileName = '';

            // Auto-hide toast after a few seconds
            setTimeout(() => {
              this.submitSuccess = false;
            }, 4000);
          } else {
            // Non-201 but no HttpErrorResponse (rare)
            this.submitError =
              'Your report was sent, but the server responded with status ' +
              response.status +
              '.';
          }
          this.isSubmitting = false;
        },
        error: (error: HttpErrorResponse) => {
          console.error(error);

          // Special handling for fake_image_detected
          if (
            error.status === 400 &&
            error.error &&
            typeof error.error === 'object' &&
            (error.error as any).error === 'fake_image_detected'
          ) {
            this.submitError =
              'Your image was flagged as fake by the AI detector.';
          } else {
            this.submitError =
              'Could not submit your incident. Please try again in a moment.';
          }

          this.isSubmitting = false;
        },
      });
  }
}
