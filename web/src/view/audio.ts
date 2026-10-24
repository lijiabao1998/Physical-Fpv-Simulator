/** Optional local oscillator, pitch and volume follow computed motor RPM. */
export class MotorAudio {
  private context:AudioContext|null=null;private oscillator:OscillatorNode|null=null;private gain:GainNode|null=null;
  async enable() {
    this.context??=new AudioContext();await this.context.resume();
    if(!this.oscillator){this.oscillator=this.context.createOscillator();this.gain=this.context.createGain();this.oscillator.type='sawtooth';this.gain.gain.value=0;this.oscillator.connect(this.gain);this.gain.connect(this.context.destination);this.oscillator.start();}
  }
  update(rpm:number,enabled:boolean) {
    if(!this.context||!this.oscillator||!this.gain)return;
    this.oscillator.frequency.setTargetAtTime(45+rpm/60*2,this.context.currentTime,.08);
    this.gain.gain.setTargetAtTime(enabled&&rpm>100?.018:0,this.context.currentTime,.04);
  }
}
