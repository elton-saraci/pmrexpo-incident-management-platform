import { ComponentFixture, TestBed } from '@angular/core/testing';

import { Jsmap } from './jsmap';

describe('Jsmap', () => {
  let component: Jsmap;
  let fixture: ComponentFixture<Jsmap>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [Jsmap]
    })
    .compileComponents();

    fixture = TestBed.createComponent(Jsmap);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
