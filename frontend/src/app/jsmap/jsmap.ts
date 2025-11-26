import {
  Component,
  ViewChild,
  ElementRef,
  Input,
  SimpleChanges,
  Output,
  EventEmitter,
} from '@angular/core';
import '@here/maps-api-for-javascript';
import onResize from 'simple-element-resize-detector';

import { FireDepartment, Incident } from '../admin-data.service';

@Component({
  selector: 'app-jsmap',
  standalone: true,
  templateUrl: './jsmap.html',
  styleUrls: ['./jsmap.scss'],
})
export class JsmapComponent {
  // Default centre: Köln Messe
  @Input() public zoom = 12;
  @Input() public lat = 50.947086;
  @Input() public lng = 6.982777;

  // Data to display
  @Input() incidents: Incident[] = [];
  @Input() fireDepartments: FireDepartment[] = [];

  @Output() notify = new EventEmitter<H.map.ChangeEvent>();

  @ViewChild('map') mapDiv?: ElementRef;

  private map?: H.Map;
  private timeoutHandle: any;

  private incidentGroup?: H.map.Group;
  private fireDeptGroup?: H.map.Group;

  // Icons
  private referenceIcon = new H.map.Icon(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 48" width="32" height="48">
      <defs>
        <linearGradient id="refGrad" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stop-color="#22c55e"/>
          <stop offset="1" stop-color="#15803d"/>
        </linearGradient>
      </defs>
      <path d="M16 0C9 0 4 5.7 4 12.8 4 23 16 36 16 36s12-13 12-23.2C28 5.7 23 0 16 0z" fill="url(#refGrad)"/>
      <circle cx="16" cy="13.5" r="4.5" fill="#f0fdf4"/>
    </svg>`
  );

  private incidentIcon = new H.map.Icon(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 48" width="32" height="48">
      <defs>
        <linearGradient id="fireGrad" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stop-color="#f97316"/>
          <stop offset="1" stop-color="#b91c1c"/>
        </linearGradient>
      </defs>
      <path d="M16 0C9 0 4 5.7 4 12.8 4 23 16 36 16 36s12-13 12-23.2C28 5.7 23 0 16 0z" fill="url(#fireGrad)"/>
      <circle cx="16" cy="14" r="5" fill="#fff3f0"/>
    </svg>`
  );

  private fireDeptIcon = new H.map.Icon(
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 48" width="32" height="48">
      <path d="M16 0C9 0 4 5.7 4 12.8 4 23 16 36 16 36s12-13 12-23.2C28 5.7 23 0 16 0z" fill="#1d4ed8"/>
      <rect x="9" y="13" width="14" height="9" fill="#eff6ff" rx="2" ry="2"/>
      <path d="M10 22h12v2H10z" fill="#1e293b"/>
    </svg>`
  );

  ngAfterViewInit(): void {
    if (!this.map && this.mapDiv) {
      const platform = new H.service.Platform({
        apikey: 'zQHJRsNzyg7C-LUyhMYG64iRkinLVCD8RlJZccLX8z0',
      });

      const layers = platform.createDefaultLayers();
      const map = new H.Map(
        this.mapDiv.nativeElement,
        (layers as any).vector.normal.map,
        {
          pixelRatio: window.devicePixelRatio,
          center: { lat: this.lat, lng: this.lng },
          zoom: this.zoom,
        }
      );

      onResize(this.mapDiv.nativeElement, () => {
        map.getViewPort().resize();
      });

      map.addEventListener('mapviewchange', (ev: H.map.ChangeEvent) => {
        this.notify.emit(ev);
      });

      new H.mapevents.Behavior(new H.mapevents.MapEvents(map));

      // Reference marker at Köln Messe (or given lat/lng)
      const refMarker = new H.map.Marker(
        { lat: this.lat, lng: this.lng },
        {
          data: { kind: 'reference' },
          icon: this.referenceIcon,
        }
      );
      map.addObject(refMarker);

      this.map = map;

      // Draw incidents + fire departments initially
      this.renderDynamicData();
    }
  }

  ngOnChanges(changes: SimpleChanges): void {
    clearTimeout(this.timeoutHandle);
    this.timeoutHandle = setTimeout(() => {
      if (!this.map) {
        return;
      }

      if (changes['zoom'] !== undefined) {
        this.map.setZoom(changes['zoom'].currentValue);
      }
      if (changes['lat'] !== undefined || changes['lng'] !== undefined) {
        this.map.setCenter({
          lat: this.lat,
          lng: this.lng,
        });
      }

      if (changes['incidents'] || changes['fireDepartments']) {
        this.renderDynamicData();
      }
    }, 100);
  }

  // ---- render incidents + fire departments ----

  private renderDynamicData(): void {
    if (!this.map) {
      return;
    }

    // Remove old groups if they exist
    if (this.incidentGroup) {
      this.map.removeObject(this.incidentGroup);
    }
    if (this.fireDeptGroup) {
      this.map.removeObject(this.fireDeptGroup);
    }

    const incidentGroup = new H.map.Group();
    const fdGroup = new H.map.Group();

    this.incidents?.forEach((incident) => {
      const marker = new H.map.Marker(
        { lat: incident.latitude, lng: incident.longitude },
        {
          data: incident,
          icon: this.incidentIcon,
        }
      );
      incidentGroup.addObject(marker);
    });

    this.fireDepartments?.forEach((fd) => {
      const marker = new H.map.Marker(
        {
          lat: fd.location.latitude,
          lng: fd.location.longitude,
        },
        {
          data: fd,
          icon: this.fireDeptIcon,
        }
      );
      fdGroup.addObject(marker);
    });

    this.map.addObject(incidentGroup);
    this.map.addObject(fdGroup);

    this.incidentGroup = incidentGroup;
    this.fireDeptGroup = fdGroup;
  }
}
