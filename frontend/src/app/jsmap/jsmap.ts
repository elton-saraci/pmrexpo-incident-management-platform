import { Component, ViewChild, ElementRef, Input, SimpleChanges, Output, EventEmitter } from '@angular/core';
import '@here/maps-api-for-javascript';
import onResize from 'simple-element-resize-detector';

@Component({
  selector: 'app-jsmap',
  standalone: true,
  templateUrl: './jsmap.html',
  styleUrls: ['./jsmap.scss']
})
export class JsmapComponent {

  @Input() public zoom = 13;
  @Input() public lat = 52.5;
  @Input() public lng = 13.4;
  
  @Output() notify = new EventEmitter();
  
  @ViewChild('map') mapDiv?: ElementRef;
  
  private heatMapLayer: H.map.layer.TileLayer;
  private map?: H.Map;

  private timeoutHandle: any;

  private minZoom = 5.8;

  private data = [
    { lat: 51.15, lng: 10.5 },
    { lat: 51.2, lng: 10.5 },
    { lat: 51.1, lng: 10.5 },
    { lat: 51.15, lng: 10.55 },
    { lat: 51.15, lng: 10.45 },
    { lat: 48, lng: 10.5 },
    { lat: 59.9245, lng: 10.954 }
  ]

  private icon = new H.map.Icon(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48" width="48" height="48" fill="none" stroke="#0F1621" stroke-width="4" stroke-linecap="round" stroke-linejoin="round">
    <path fill="#00AFAA" d="M24 4C16.26 4 10 10.26 10 18c0 9.74 14 26 14 26s14-16.26 14-26c0-7.74-6.26-14-14-14z"/>
    <circle cx="24" cy="18" r="6" fill="#1D1E1F"/>
  </svg>`);


  ngAfterViewInit(): void {
    const coords = {lat: 52, lng: 10.5};
    const marker = new H.map.Marker(coords, { data: null, icon: this.icon });

    if (!this.map && this.mapDiv) {
      // Instantiate a platform, default layers and a map as usual.
      const platform = new H.service.Platform({
        apikey: 'zQHJRsNzyg7C-LUyhMYG64iRkinLVCD8RlJZccLX8z0'
      });
      const layers = platform.createDefaultLayers();
      const map = new H.Map(
        this.mapDiv.nativeElement,
        // Add type assertion to the layers object...
        // ...to avoid any Type errors during compilation.
        (layers as any).vector.normal.map,
        {
          pixelRatio: window.devicePixelRatio,
          center: {lat: 51.15, lng: 10.5},
          zoom: 5.8,
        },
      );
      onResize(this.mapDiv.nativeElement, () => {
        map.getViewPort().resize();
      }); // Sets up the event listener to handle resizing

      // Create a provider for a semi-transparent heat map
      const heatmapProvider = new H.data.heatmap.Provider({
        colors: new H.data.heatmap.Colors(
          {
            0: "blue",
            0.5: "red",
            1: "yellow",
          },
          true
        ),
        opacity: 0.9,
        // Paint assumed values in regions where no data is available
        assumeValues: false,
      });

      // Add the data:
      heatmapProvider.addData(this.data);

      // Add a layer for the heatmap provider to the map
      this.heatMapLayer = new H.map.layer.TileLayer(heatmapProvider);
      map.addLayer(this.heatMapLayer);
      map.addObject(marker);

      map.addEventListener('mapviewchange', (ev: H.map.ChangeEvent) => {
        this.notify.emit(ev);
      });
      new H.mapevents.Behavior(new H.mapevents.MapEvents(map));

      this.map = map;
    }
  }

  ngOnChanges(changes: SimpleChanges) {
    console.log("hello")
    clearTimeout(this.timeoutHandle);
    this.timeoutHandle = setTimeout(() => {
      if (this.map) {
        if (changes['zoom'] !== undefined) {
          console.log("IN MAP")
          console.log(changes['zoom']);
          this.map.setZoom(changes['zoom'].currentValue);
        }
        if (changes['lat'] !== undefined) {
          this.map.setCenter({lat: changes['lat'].currentValue, lng: this.lng});
        }
        if (changes['lng'] !== undefined) {
          this.map.setCenter({lat: this.lat, lng: changes['lng'].currentValue});
        }
      }
    }, 100);
  }

  changeToPins(pins: boolean) {
    if(pins) {
      this.map?.removeLayer(this.heatMapLayer);
      this.addMarkers();
    } else {
      this.map.addLayer(this.heatMapLayer);
      this.removeMarkers();
    }
  }

  private addMarkers() {
    this.data.forEach(point => {
      this.map.addObject(new H.map.Marker(point, { data: null, icon: this.icon }))
    })
  }

  private removeMarkers() {
    this.map.getObjects().forEach(element => {
      this.map.removeObject(element);
    });
  }
}
