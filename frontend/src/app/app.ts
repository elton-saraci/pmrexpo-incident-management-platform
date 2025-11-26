import { Component, ViewChild } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { JsmapComponent } from './jsmap/jsmap';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [JsmapComponent], // Adds MappositionComponent to the AppComponent template
  templateUrl: './app.html',
  styleUrls: ['./app.scss']
})
export class AppComponent {
  @ViewChild('map') map: JsmapComponent;

  title = 'jsapi-angular';

  zoom: number = 5.8;
  lat: number = 51.5;
  lng: number = 10.5;

  private minZoom = 5.8;
  private showPins: boolean = false;

  // Updates the zoom, lat, and lng properties based on user input.
  handleInputChange(event: H.map.ChangeEvent) {
    // console.log("handling input")
    // console.log(event);
    // const target = <HTMLInputElement> event.target;
    // if (target) {
    //   console.log(target);
    //   if (target.name === 'zoom') {
    //     console.log("geht")
    //     this.zoom = parseFloat(target.value);
    //   }
    //   if (target.name === 'lat') {
    //     console.log("der")
    //     this.lat = parseFloat(target.value);
    //   }
    //   if (target.name === 'lng') {
    //     console.log("rein")
    //     this.lng = parseFloat(target.value);
    //   }
    // }
    // console.log(event.newValue.lookAt.zoom);
    // console.log(event.newValue.lookAt.zoom);
    // this.zoom = event.newValue.lookAt.zoom;
    // if(event.newValue.lookAt.zoom > this.minZoom) {
    //   this.zoom = this.minZoom;
    //   // console.log("SETTING TO MAX");
    //   this.zoom += 0.1;
    // }

    if(event.newValue.lookAt.zoom >= 11 && this.showPins == false) {
      console.log("CHANGE TO PINS")
      this.map.changeToPins(true);
      this.showPins = true;
    } else if (event.newValue.lookAt.zoom < 11 && this.showPins == true){
      this.map.changeToPins(false);
      this.showPins = false;
      console.log("change to heatmap")
    }
  }
}
