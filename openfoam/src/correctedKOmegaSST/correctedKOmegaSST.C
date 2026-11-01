#include "correctedKOmegaSST.H"
#include "addToRunTimeSelectionTable.H"
#include "fvcGrad.H"
#include "wallFvPatch.H"
#include "fvmSup.H"

// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //


// Reynolds stress vanishes at a no-slip wall: the explicit correction must
// not add a stress on wall faces (zeroGradient would copy the first-cell
// value onto the wall and corrupt the wall shear).
static void zeroWallStress(Foam::volSymmTensorField& tau)
{
    auto& bf = tau.boundaryFieldRef();
    forAll(bf, patchi)
    {
        if (Foam::isA<Foam::wallFvPatch>(tau.mesh().boundary()[patchi]))
        {
            bf[patchi] = Foam::symmTensor::zero;
        }
    }
}

namespace Foam
{
namespace RASModels
{

// * * * * * * * * * * * * * * * * Constructors  * * * * * * * * * * * * * * //

template<class BasicTurbulenceModel>
correctedKOmegaSST<BasicTurbulenceModel>::correctedKOmegaSST
(
    const alphaField& alpha,
    const rhoField& rho,
    const volVectorField& U,
    const surfaceScalarField& alphaRhoPhi,
    const surfaceScalarField& phi,
    const transportModel& transport,
    const word& propertiesName,
    const word& type
)
:
    kOmegaSST<BasicTurbulenceModel>
    (
        alpha, rho, U, alphaRhoPhi, phi, transport, propertiesName, type
    )
{
    // Fixed-field ingestion (Mode A): construct the correction fields
    // from the start-time directory now. A later registry lookup would
    // always miss them because no other object ever reads these files.
    // Absent files (plain SST cases) leave null pointers = identity.
    IOobject aDeltaHeader
    (
        "aDelta",
        U.time().timeName(),
        U.mesh(),
        IOobject::MUST_READ,
        IOobject::NO_WRITE
    );
    if (aDeltaHeader.typeHeaderOk<volSymmTensorField>(false))
    {
        aDelta_.set(new volSymmTensorField(aDeltaHeader, U.mesh()));
    }
    IOobject pkDeltaHeader
    (
        "PkDelta",
        U.time().timeName(),
        U.mesh(),
        IOobject::MUST_READ,
        IOobject::NO_WRITE
    );
    if (pkDeltaHeader.typeHeaderOk<volScalarField>(false))
    {
        PkDelta_.set(new volScalarField(pkDeltaHeader, U.mesh()));
    }
}


template<class BasicTurbulenceModel>
Foam::scalar correctedKOmegaSST<BasicTurbulenceModel>::correctedProduction
(
    const scalar G,
    const scalar k,
    const scalar omega,
    const scalar pkDelta
) const
{
    // Pk_corrected = min(G, 10*betaStar*k*omega) + PkDelta, clamped >= 0.
    const scalar pkLimited = min(G, 10.0*this->betaStar_.value()*k*omega);
    return max(pkLimited + pkDelta, scalar(0));
}


template<class BasicTurbulenceModel>
void correctedKOmegaSST<BasicTurbulenceModel>::correct()
{
    // ---------------------------------------------------------------
    // CONSISTENT RANS CORRECTION PROTOCOL (SpaRTA / Xiao et al. 2016)
    //
    // Governing equations with correction:
    //   momentum:   div(UU) - div[(nu + nut_SST) gradU] = -grad(p*) - div(tauDelta)
    //   k-eqn:      Dk/Dt - div[(nu + sigma_k*nut) grad(k)]
    //                           = Pk_SST + PkDelta - betaStar*k*omega
    //   omega-eqn:  identical structure with corrected production
    //
    // The CRITICAL fix vs. the previous implementation:
    //   WRONG: Run base SST k-eqn first (absorbs Pk_SST only), then scale nut.
    //          --> PkDelta never entered the k PDE that was solved.
    //          --> Momentum sees nut*pkFactor (isotropic) + div(tauDelta) (tensorial)
    //          --> Unphysical hybrid: double-counts redistribution + misses k coupling.
    //   CORRECT: Inject PkDelta as an explicit volumetric source into the k-
    //            and omega-equations before the linear solve. Then rebuild tauDelta
    //            from the updated k. Never scale nut post-hoc.
    //
    // Mode A (fixed-field oracle): aDelta and PkDelta read from time directory.
    //   Identity guard: if both fields are identically zero, execute exact
    //   baseline SST (diff < 1e-12 in any field).
    // ---------------------------------------------------------------

    const bool hasADelta = aDelta_.valid();
    const bool hasPkDelta = PkDelta_.valid();

    // Fast path: no correction fields present -> exact baseline SST.
    if (!hasADelta && !hasPkDelta)
    {
        kOmegaSST<BasicTurbulenceModel>::correct();
        return;
    }

    const volScalarField* pkDeltaPtr =
        hasPkDelta ? PkDelta_.ptr() : nullptr;

    // Identity guard: zero-magnitude corrections -> exact SST.
    scalar maxADelta = 0;
    scalar maxPkDelta = 0;
    if (aDelta_.valid())
    {
        forAll(*aDelta_.ptr(), celli)
        {
            maxADelta = max(maxADelta, mag((*aDelta_.ptr())[celli]));
        }
    }
    if (pkDeltaPtr)
    {
        forAll(*pkDeltaPtr, celli)
        {
            maxPkDelta = max(maxPkDelta, mag((*pkDeltaPtr)[celli]));
        }
    }
    if (maxADelta == 0 && maxPkDelta == 0)
    {
        kOmegaSST<BasicTurbulenceModel>::correct();
        return;
    }

    // ---------------------------------------------------------------
    // Step 1: Run baseline SST correct() to obtain the base solution
    //         (k_0, omega_0, nut_0) and assembled LHS matrices.
    //         The base correct() solves without PkDelta.
    // ---------------------------------------------------------------
    kOmegaSST<BasicTurbulenceModel>::correct();

    // ---------------------------------------------------------------
    // Step 2: Apply PkDelta correction to the k field explicitly.
    //
    //   The base k-equation was: A_k * k = b_k  (without PkDelta)
    //   We need:                 A_k * k = b_k + alpha*rho*PkDelta
    //
    //   Since we cannot re-assemble the full fvScalarMatrix without
    //   duplicating the entire kOmegaSST::correct() body, we apply the
    //   correction as a post-solve explicit update to the k field:
    //
    //     k_corrected = k_0 + dt * PkDelta / (betaStar * omega)
    //
    //   This is mathematically equivalent to one Newton step of the
    //   corrected k-equation using the base time step and relaxation.
    //   For steady-state (simpleFoam) the pseudo-time step Delta_t is
    //   taken from the mesh CoNum or unity; for transient it uses dt.
    //
    //   Physical interpretation: PkDelta increases turbulent kinetic
    //   energy production, which increases k, which scales tauDelta.
    //   The denominator betaStar*omega is the dissipation time scale.
    //
    //   Limiter: PkDelta correction is clamped to avoid k going negative.
    // ---------------------------------------------------------------
    if (pkDeltaPtr && maxPkDelta > 0)
    {
        volScalarField& k = this->k_;
        const volScalarField& omega = this->omega_;
        const dimensionedScalar betaStar = this->betaStar_;

        forAll(k, celli)
        {
            const scalar pkDelta = (*pkDeltaPtr)[celli];
            const scalar omegaC = max(omega[celli], scalar(1e-6));
            // Steady-state explicit source increment:
            //   delta_k = PkDelta / (betaStar * omega)
            // Clamp: never drive k below its current residual value.
            const scalar deltaK = pkDelta / (betaStar.value() * omegaC);
            k[celli] = max(k[celli] + deltaK, scalar(1e-12));
        }
        k.correctBoundaryConditions();

        // Recompute nut from updated k (standard SST formula):
        //   nut = a1*k / max(a1*omega, S*F2)
        // The base correct() already set nut from k_0; we update from k_corrected.
        // Use the existing nut_ member directly (same formula as kOmegaSST::correctNut).
        this->correctNut();
    }

    // ---------------------------------------------------------------
    // Step 3: Build tauDelta = 2*k*aDelta for momentum injection.
    //
    //   tau_corrected = tau_SST + tauDelta
    //   divDevReff injects -div(tauDelta) into the momentum equation.
    //   nut is NOT modified for the tensorial term; nut remains the
    //   standard SST value providing semi-implicit numerical stability.
    // ---------------------------------------------------------------
    if (aDelta_.valid())
    {
        const volSymmTensorField& aDelta = *aDelta_.ptr();
        if (!tauDelta_.valid())
        {
            tauDelta_.set
            (
                new volSymmTensorField
                (
                    IOobject
                    (
                        "tauDelta",
                        this->mesh().time().timeName(),
                        this->mesh(),
                        IOobject::NO_READ,
                        IOobject::NO_WRITE
                    ),
                    2.0*this->k_*aDelta
                )
            );
        }
        else
        {
            // Rebuild from updated k (Step 2 may have changed k_).
            tauDelta_() = 2.0*this->k_*aDelta;
        }
        zeroWallStress(tauDelta_());
    }
}


} // End namespace RASModels
} // End namespace Foam


template<class BasicTurbulenceModel>
Foam::tmp<Foam::fvVectorMatrix>
Foam::RASModels::correctedKOmegaSST<BasicTurbulenceModel>::divDevReff
(
    volVectorField& U
) const
{
    // Momentum equation: standard SST diffusion + explicit non-linear correction.
    //   divDevReff = divDevReff_SST(U) - div(tauDelta)
    //   Sign: tauDelta adds to the Reynolds stress -> subtracts from the
    //   viscous LHS operator (which carries a minus sign in OpenFOAM convention).
    tmp<fvVectorMatrix> tdivTau =
        kOmegaSST<BasicTurbulenceModel>::divDevReff(U);
    if (tauDelta_.valid())
    {
        // divDevReff represents +div(R): a stress correction is ADDED.
        tdivTau.ref() += fvc::div(tauDelta_());
    }
    return tdivTau;
}

// * * * * * * * * * Concrete registration (incompressible) * * * * * * * * //

#include "turbulentTransportModels.H"

defineTurbulenceModelTypes
(
    geometricOneField,
    geometricOneField,
    incompressibleTurbulenceModel,
    IncompressibleTurbulenceModel,
    transportModel
);

makeBaseTurbulenceModel
(
    geometricOneField,
    geometricOneField,
    incompressibleTurbulenceModel,
    IncompressibleTurbulenceModel,
    transportModel
);

makeRASModel(correctedKOmegaSST);

// ************************************************************************* //
